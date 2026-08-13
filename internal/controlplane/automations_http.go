package controlplane

import (
	"database/sql"
	"encoding/base64"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

func (a *API) listAutomationStatus(w http.ResponseWriter, r *http.Request) {
	page, err := a.store.AutomationsPage(r.Context(), protocol.MaxAutomationPageSize, nil)
	if err != nil {
		writeError(w, err)
		return
	}
	now := time.Now().UTC()
	statuses := make([]protocol.AutomationStatus, 0, len(page.Automations)+5)
	for _, automation := range page.Automations {
		status := "нет данных"
		result := automation.Health.Message
		if result == "" {
			result = "Проверка ещё не вернула результат."
		}
		switch automation.Health.Status {
		case "healthy", "checking":
			status = "живая"
		case "disabled", "blocked":
			status = "стоит"
		case "error":
			status = "сломана"
		}
		lastSeen := automation.LastCheckedAt
		stale := lastSeen != nil && now.Sub(*lastSeen) > 5*time.Minute
		if stale {
			status = "сломана"
			result = "Данные устарели: последняя проверка старше пяти минут. " + result
		}
		statuses = append(statuses, protocol.AutomationStatus{Key: "automation:" + automation.ID, Name: automation.Title, Source: "пользовательская автоматика", Status: status, LastResult: result, LastSeen: lastSeen, Stale: stale})
	}
	statuses = append(statuses, a.internalAutomationStatuses(r, now)...)
	writeJSON(w, http.StatusOK, protocol.AutomationStatusPage{Automations: statuses, SnapshotAt: now})
}

func (a *API) internalAutomationStatuses(r *http.Request, now time.Time) []protocol.AutomationStatus {
	missing := func(key, name, source, message string) protocol.AutomationStatus {
		return protocol.AutomationStatus{Key: key, Name: name, Source: source, Status: "нет данных", LastResult: message}
	}
	pilot := missing("factory:pilot", "Конвейер Factory", "pilot", "Настройки pilot недоступны.")
	brain := missing("factory:brain", "Мозг Factory", "brain chain", "Цепочка моделей не настроена или недоступна.")
	if a.pilotConfig != nil {
		if settings, err := a.pilotConfig.Read(); err == nil {
			if settings.Settings.Enabled {
				pilot.Status, pilot.LastResult = "живая", "Pilot включён и принимает новые работы."
			} else {
				pilot.Status, pilot.LastResult = "стоит", "Pilot отключён в настройках."
			}
			if len(settings.Settings.BrainChain) > 0 {
				brain.Status, brain.LastResult = "живая", "Настроена цепочка моделей для обработки работ."
			}
		} else {
			pilot.LastResult = "Настройки pilot недоступны: " + err.Error()
		}
	}
	release := missing("factory:release-broker", "Посредник выпуска", "release broker", "Нет записей о последней операции выпуска.")
	deploy := missing("factory:deploy", "Службы выката", "deploy services", "Нет записей о последнем выкате.")
	var updated int64
	var state, message string
	err := a.store.db.QueryRowContext(r.Context(), `SELECT updated_at,status,message FROM project_operations ORDER BY updated_at DESC LIMIT 1`).Scan(&updated, &state, &message)
	if err == nil {
		seen := time.UnixMilli(updated).UTC()
		status := "живая"
		if state != "succeeded" {
			status = "сломана"
		}
		release = protocol.AutomationStatus{Key: release.Key, Name: release.Name, Source: release.Source, Status: status, LastResult: message, LastSeen: &seen, Stale: now.Sub(seen) > 24*time.Hour}
		deploy = protocol.AutomationStatus{Key: deploy.Key, Name: deploy.Name, Source: deploy.Source, Status: status, LastResult: message, LastSeen: &seen, Stale: now.Sub(seen) > 24*time.Hour}
		if release.Stale {
			release.Status = "сломана"
			deploy.Status = "сломана"
		}
	} else if !errors.Is(err, sql.ErrNoRows) {
		release.LastResult = "Журнал выпуска недоступен."
		deploy.LastResult = "Журнал выката недоступен."
	}
	janitor := missing("factory:janitor", "Уборщик рабочих каталогов", "janitor", "Журнал janitor пока не ведётся.")
	return []protocol.AutomationStatus{pilot, brain, release, deploy, janitor}
}

func (a *API) listAutomations(w http.ResponseWriter, r *http.Request) {
	limit, err := pageLimit(r, protocol.DefaultAutomationPageSize, protocol.MaxAutomationPageSize)
	if err != nil {
		writeError(w, err)
		return
	}
	if len(r.URL.Query()["limit"]) > 1 {
		writeError(w, invalid("invalid_query", "limit may be provided once"))
		return
	}
	var cursor *protocol.AutomationCursor
	if encoded := r.URL.Query().Get("cursor"); encoded != "" {
		decoded, err := decodeAutomationCursor(encoded)
		if err != nil {
			writeError(w, invalid("invalid_cursor", "cursor is invalid"))
			return
		}
		cursor = &decoded
	}
	if len(r.URL.Query()["cursor"]) > 1 {
		writeError(w, invalid("invalid_query", "cursor may be provided once"))
		return
	}
	page, err := a.store.AutomationsPage(r.Context(), limit, cursor)
	if err != nil {
		writeError(w, err)
		return
	}
	var nextCursor *string
	if page.NextCursor != nil {
		encoded, err := encodeAutomationCursor(*page.NextCursor)
		if err != nil {
			writeError(w, unavailable(err))
			return
		}
		nextCursor = &encoded
	}
	writeJSON(w, http.StatusOK, map[string]any{"automations": page.Automations, "next_cursor": nextCursor})
}

func (a *API) createAutomation(w http.ResponseWriter, r *http.Request) {
	if !prepareMutation(w, r, protocol.MaxBodyBytes) {
		return
	}
	var input protocol.CreateAutomationRequest
	if !decodeJSON(w, r, &input) {
		return
	}
	detail, created, err := a.store.CreateAutomation(r.Context(), input)
	if err != nil {
		writeError(w, err)
		return
	}
	status := http.StatusOK
	if created {
		status = http.StatusCreated
	}
	writeJSON(w, status, detail)
}

func (a *API) getAutomation(w http.ResponseWriter, r *http.Request) {
	detail, err := a.store.Automation(r.Context(), r.PathValue("automation_id"))
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

func (a *API) updateAutomation(w http.ResponseWriter, r *http.Request) {
	if !prepareMutation(w, r, protocol.MaxBodyBytes) {
		return
	}
	var input protocol.UpdateAutomationRequest
	if !decodeJSON(w, r, &input) {
		return
	}
	detail, err := a.store.UpdateAutomation(r.Context(), r.PathValue("automation_id"), input)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, detail)
}

func (a *API) setAutomationEnabled(w http.ResponseWriter, r *http.Request) {
	if !prepareMutation(w, r, protocol.MaxBodyBytes) {
		return
	}
	var input protocol.SetAutomationEnabledRequest
	if !decodeJSON(w, r, &input) {
		return
	}
	if input.Enabled == nil {
		writeError(w, invalid("invalid_automation_enabled", "enabled is required"))
		return
	}
	id := r.PathValue("automation_id")
	detail, invalidatedToken, err := a.store.setAutomationEnabled(r.Context(), id, *input.Enabled, input.ConfirmLegacyPollerStopped)
	if err != nil {
		writeError(w, err)
		return
	}
	if !*input.Enabled {
		a.automations.Cancel(id, invalidatedToken)
	}
	a.automations.Wake()
	writeJSON(w, http.StatusOK, detail)
}

func (a *API) provisionPipelinePatrol(w http.ResponseWriter, r *http.Request) {
	if !prepareMutation(w, r, protocol.MaxBodyBytes) {
		return
	}
	var input struct{}
	if !decodeJSON(w, r, &input) {
		return
	}
	detail, err := a.store.ProvisionPipelinePatrol(r.Context(), r.PathValue("automation_id"))
	if err != nil {
		writeError(w, err)
		return
	}
	a.automations.Wake()
	writeJSON(w, http.StatusOK, detail)
}

func (a *API) testAutomation(w http.ResponseWriter, r *http.Request) {
	if !prepareMutation(w, r, protocol.MaxBodyBytes) {
		return
	}
	var input struct{}
	if !decodeJSON(w, r, &input) {
		return
	}
	result, err := a.automations.Test(r.Context(), r.PathValue("automation_id"))
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (a *API) checkAutomation(w http.ResponseWriter, r *http.Request) {
	if !prepareMutation(w, r, protocol.MaxBodyBytes) {
		return
	}
	var input struct{}
	if !decodeJSON(w, r, &input) {
		return
	}
	detail, err := a.store.RequestAutomationCheck(r.Context(), r.PathValue("automation_id"))
	if err != nil {
		writeError(w, err)
		return
	}
	a.automations.Wake()
	writeJSON(w, http.StatusAccepted, detail)
}

func (a *API) runAutomation(w http.ResponseWriter, r *http.Request) {
	if !prepareMutation(w, r, protocol.MaxBodyBytes) {
		return
	}
	var input protocol.RunAutomationRequest
	if !decodeJSON(w, r, &input) {
		return
	}
	detail, err := a.automations.RunNow(r.Context(), r.PathValue("automation_id"), input)
	if err != nil {
		writeError(w, err)
		return
	}
	a.automations.Wake()
	writeJSON(w, http.StatusAccepted, detail)
}

func (a *API) listAutomationOccurrences(w http.ResponseWriter, r *http.Request) {
	limit := protocol.DefaultAutomationPageSize
	if raw := r.URL.Query().Get("limit"); raw != "" {
		value, err := strconv.Atoi(raw)
		if err != nil || value < 1 || value > protocol.MaxAutomationPageSize {
			writeError(w, invalid("invalid_limit", "limit must be between 1 and 200"))
			return
		}
		limit = value
	}
	if len(r.URL.Query()["limit"]) > 1 {
		writeError(w, invalid("invalid_query", "limit may be provided once"))
		return
	}
	var cursor *protocol.AutomationOccurrenceCursor
	if encoded := r.URL.Query().Get("cursor"); encoded != "" {
		decoded, err := decodeAutomationOccurrenceCursor(encoded)
		if err != nil {
			writeError(w, invalid("invalid_cursor", "cursor is invalid"))
			return
		}
		cursor = &decoded
	}
	if len(r.URL.Query()["cursor"]) > 1 {
		writeError(w, invalid("invalid_query", "cursor may be provided once"))
		return
	}
	page, err := a.store.AutomationOccurrencesPage(r.Context(), r.PathValue("automation_id"), limit, cursor)
	if err != nil {
		writeError(w, err)
		return
	}
	var nextCursor *string
	if page.NextCursor != nil {
		encoded, err := encodeAutomationOccurrenceCursor(*page.NextCursor)
		if err != nil {
			writeError(w, unavailable(err))
			return
		}
		nextCursor = &encoded
	}
	writeJSON(w, http.StatusOK, map[string]any{"occurrences": page.Occurrences, "next_cursor": nextCursor})
}

func encodeAutomationCursor(cursor protocol.AutomationCursor) (string, error) {
	return encodeOpaqueCursor(cursor)
}

func decodeAutomationCursor(encoded string) (protocol.AutomationCursor, error) {
	var cursor protocol.AutomationCursor
	if err := decodeOpaqueCursor(encoded, &cursor); err != nil {
		return cursor, err
	}
	if cursor.UpdatedAtMillis <= 0 || strings.TrimSpace(cursor.ID) == "" {
		return cursor, errors.New("invalid Automation cursor")
	}
	return cursor, nil
}

func encodeAutomationOccurrenceCursor(cursor protocol.AutomationOccurrenceCursor) (string, error) {
	return encodeOpaqueCursor(cursor)
}

func decodeAutomationOccurrenceCursor(encoded string) (protocol.AutomationOccurrenceCursor, error) {
	var cursor protocol.AutomationOccurrenceCursor
	if err := decodeOpaqueCursor(encoded, &cursor); err != nil {
		return cursor, err
	}
	if cursor.CreatedAtMillis <= 0 || strings.TrimSpace(cursor.ID) == "" {
		return cursor, errors.New("invalid Automation Occurrence cursor")
	}
	return cursor, nil
}

func encodeOpaqueCursor(cursor any) (string, error) {
	body, err := json.Marshal(cursor)
	if err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(body), nil
}

func decodeOpaqueCursor(encoded string, cursor any) error {
	body, err := base64.RawURLEncoding.DecodeString(encoded)
	if err != nil {
		return err
	}
	return json.Unmarshal(body, cursor)
}

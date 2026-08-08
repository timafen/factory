package controlplane

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// Access grants: what the factory as a whole is allowed to touch on the server.
// Two files decide it. policy.json is root-owned and says which scopes may be
// switched from the UI at all; access.json is the switchboard state the owner
// flips here. The fx broker on the server reads both before doing anything.

var accessMu sync.Mutex

type accessScope struct {
	Key         string `json:"key"`
	Title       string `json:"title"`
	Description string `json:"description"`
	Enabled     bool   `json:"enabled"`
	UIToggle    bool   `json:"ui_toggleable"`
	UpdatedAt   string `json:"updated_at"`
	Note        string `json:"note"`
	GrantCmd    string `json:"grant_command"`
	RevokeCmd   string `json:"revoke_command"`
	GrantAlt    string `json:"grant_command_alt"`
	RevokeAlt   string `json:"revoke_command_alt"`
}

var accessCatalog = []struct {
	Key, Title, Description string
}{
	{"staging", "Staging", "Читать логи и статус, перезапускать сервисы staging, накатывать миграции и собирать статику. Боевой сайт недоступен."},
	{"production-readonly", "Прод — только чтение", "Смотреть статус, логи и имена переменных боевого контура. Ничего менять нельзя."},
	{"production-write", "Прод — запись", "Выкат в прод. Включается только на самом сервере: интерфейс и агенты работают под одним пользователем, поэтому веб-переключателю здесь доверять нельзя."},
	{"root", "Полный root", "Не выдаётся из интерфейса ни при каких условиях."},
}

func accessGrantsPath() string {
	home := os.Getenv("FACTORY_DATA_HOME")
	if home == "" {
		home = "/opt/factory-data"
	}
	return filepath.Join(home, "pilot", "access.json")
}

const accessPolicyPath = "/etc/factory-access/policy.json"

func readAccessPolicy() map[string]any {
	out := map[string]any{}
	data, err := os.ReadFile(accessPolicyPath)
	if err != nil {
		return out
	}
	_ = json.Unmarshal(data, &out)
	return out
}

func dangerousEnabled(policy map[string]any, key string) bool {
	list, _ := policy["enabled_dangerous"].([]any)
	for _, v := range list {
		if s, ok := v.(string); ok && s == key {
			return true
		}
	}
	return false
}

func policyAllowsUI(policy map[string]any, key string) bool {
	list, _ := policy["ui_toggleable"].([]any)
	for _, v := range list {
		if s, ok := v.(string); ok && s == key {
			return true
		}
	}
	return false
}

func readAccessGrants() map[string]any {
	out := map[string]any{}
	data, err := os.ReadFile(accessGrantsPath())
	if err != nil {
		return out
	}
	_ = json.Unmarshal(data, &out)
	return out
}

func grantEnabled(grants map[string]any, key string) (bool, string, string) {
	switch v := grants[key].(type) {
	case bool:
		return v, "", ""
	case map[string]any:
		on, _ := v["enabled"].(bool)
		at, _ := v["updated_at"].(string)
		note, _ := v["note"].(string)
		return on, at, note
	}
	return false, "", ""
}

func (a *API) listAccess(w http.ResponseWriter, r *http.Request) {
	accessMu.Lock()
	defer accessMu.Unlock()
	policy := readAccessPolicy()
	grants := readAccessGrants()
	out := make([]accessScope, 0, len(accessCatalog))
	for _, c := range accessCatalog {
		on, at, note := grantEnabled(grants, c.Key)
		ui := policyAllowsUI(policy, c.Key)
		scope := accessScope{
			Key: c.Key, Title: c.Title, Description: c.Description,
			Enabled: on, UIToggle: ui, UpdatedAt: at, Note: note,
		}
		if !ui {
			scope.Enabled = dangerousEnabled(policy, c.Key)
			scope.GrantCmd = "ssh root@212.28.186.194 'fx-policy allow " + c.Key + "'"
			scope.RevokeCmd = "ssh root@212.28.186.194 'fx-policy deny " + c.Key + "'"
			scope.GrantAlt = "ssh timafen@212.28.186.194 'sudo fx-policy allow " + c.Key + "'"
			scope.RevokeAlt = "ssh timafen@212.28.186.194 'sudo fx-policy deny " + c.Key + "'"
		}
		out = append(out, scope)
	}
	writeJSON(w, http.StatusOK, map[string]any{"scopes": out})
}

type accessRequest struct {
	Enabled bool   `json:"enabled"`
	Note    string `json:"note"`
}

func (a *API) setAccess(w http.ResponseWriter, r *http.Request) {
	key := r.PathValue("scope")
	known := false
	for _, c := range accessCatalog {
		if c.Key == key {
			known = true
			break
		}
	}
	if !known {
		writeError(w, invalid("bad_scope", "unknown access scope"))
		return
	}
	var req accessRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, invalid("bad_body", "expected {\"enabled\": true|false}"))
		return
	}
	accessMu.Lock()
	defer accessMu.Unlock()
	if !policyAllowsUI(readAccessPolicy(), key) {
		writeError(w, invalid("not_ui_toggleable",
			"этот доступ не переключается из интерфейса — только на сервере"))
		return
	}
	grants := readAccessGrants()
	note := req.Note
	if len(note) > 200 {
		note = note[:200]
	}
	grants[key] = map[string]any{
		"enabled":    req.Enabled,
		"updated_at": time.Now().UTC().Format(time.RFC3339),
		"note":       note,
	}
	data, err := json.MarshalIndent(grants, "", " ")
	if err != nil {
		writeError(w, unavailable(err))
		return
	}
	if err := os.WriteFile(accessGrantsPath(), data, 0o644); err != nil {
		writeError(w, unavailable(err))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "scope": key, "enabled": req.Enabled})
}

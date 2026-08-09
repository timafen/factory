package controlplane

import (
	"context"
	"fmt"
	"net/http"
	"strings"
)

const maxWorkHistoryTasks = 100

type workHistoryEntry struct {
	TaskID string `json:"task_id"`
	Text   string `json:"text"`
}

type workAttemptState struct {
	number int
	state  string
}

func (a *API) getWorkHistory(w http.ResponseWriter, r *http.Request) {
	taskIDs := r.URL.Query()["task_id"]
	if len(taskIDs) == 0 || len(taskIDs) > maxWorkHistoryTasks {
		writeError(w, invalid("invalid_task_ids", "task_id must be provided between 1 and 100 times"))
		return
	}
	seen := make(map[string]bool, len(taskIDs))
	for _, taskID := range taskIDs {
		if strings.TrimSpace(taskID) == "" || seen[taskID] {
			writeError(w, invalid("invalid_task_ids", "task_id values must be nonblank and unique"))
			return
		}
		seen[taskID] = true
	}

	history, err := a.store.workHistory(r.Context(), taskIDs)
	if err != nil {
		writeError(w, err)
		return
	}
	entries := make([]workHistoryEntry, 0, len(taskIDs))
	for _, taskID := range taskIDs {
		entries = append(entries, workHistoryEntry{TaskID: taskID, Text: describeWorkAttempts(history[taskID])})
	}
	writeJSON(w, http.StatusOK, map[string]any{"history": entries})
}

// workHistory deliberately selects only attempt number and state. Prompts,
// context, result, error, event payloads and other internal data cannot enter
// the owner-facing response because they never leave the database.
func (s *Store) workHistory(ctx context.Context, taskIDs []string) (map[string][]workAttemptState, error) {
	placeholders := strings.TrimSuffix(strings.Repeat("?,", len(taskIDs)), ",")
	arguments := make([]any, len(taskIDs))
	for index, taskID := range taskIDs {
		arguments[index] = taskID
	}
	rows, err := s.db.QueryContext(ctx, `
		SELECT execution.task_id, attempt.attempt_number, attempt.state
		FROM executions execution
		JOIN attempts attempt ON attempt.execution_id = execution.id
		WHERE execution.task_id IN (`+placeholders+`)
		ORDER BY execution.task_id, attempt.attempt_number
	`, arguments...)
	if err != nil {
		return nil, unavailable(err)
	}
	defer rows.Close()
	history := make(map[string][]workAttemptState, len(taskIDs))
	for rows.Next() {
		var taskID string
		var attempt workAttemptState
		if err := rows.Scan(&taskID, &attempt.number, &attempt.state); err != nil {
			return nil, unavailable(err)
		}
		history[taskID] = append(history[taskID], attempt)
	}
	if err := rows.Err(); err != nil {
		return nil, unavailable(err)
	}
	return history, nil
}

func describeWorkAttempts(attempts []workAttemptState) string {
	if len(attempts) == 0 {
		return "Ожидает начала работы."
	}
	parts := make([]string, 0, len(attempts))
	for _, attempt := range attempts {
		state := map[string]string{
			"preparing": "подготовка",
			"running":   "выполняется",
			"succeeded": "завершена успешно",
			"failed":    "завершилась неудачно",
			"cancelled": "отменена",
			"lost":      "прервана",
		}[attempt.state]
		if state == "" {
			state = "состояние обновлено"
		}
		parts = append(parts, fmt.Sprintf("Попытка %d: %s", attempt.number, state))
	}
	return strings.Join(parts, "; ") + "."
}

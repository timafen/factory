package controlplane

import "net/http"

// Work history deliberately exposes a short outcome, not the worker's report.
// The latter can contain command output and implementation details that make the
// board unreadable; the task screen remains the place for technical diagnostics.
type workHistoryEntry struct {
	TaskID string `json:"task_id"`
	Text   string `json:"text"`
}

func (a *API) getWorkHistory(w http.ResponseWriter, r *http.Request) {
	ids := r.URL.Query()["task_id"]
	if len(ids) == 0 || len(ids) > 200 {
		writeError(w, invalid("invalid_task_ids", "provide between 1 and 200 task_id values"))
		return
	}

	entries := make([]workHistoryEntry, 0, len(ids))
	for _, id := range ids {
		task, err := a.store.Task(r.Context(), id)
		if err != nil {
			writeError(w, err)
			return
		}
		entries = append(entries, workHistoryEntry{TaskID: id, Text: plainWorkHistory(task.Task.State)})
	}
	writeJSON(w, http.StatusOK, map[string]any{"history": entries})
}

func plainWorkHistory(state string) string {
	switch state {
	case "queued":
		return "ждёт исполнителя"
	case "running":
		return "исполнитель работает"
	case "succeeded":
		return "этап завершён"
	case "failed":
		return "этап завершился с ошибкой"
	case "cancelled":
		return "этап отменён"
	default:
		return "состояние уточняется"
	}
}

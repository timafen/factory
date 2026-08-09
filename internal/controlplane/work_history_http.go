package controlplane

import (
	"errors"
	"net/http"
	"strings"

	"github.com/owainlewis/factory/internal/protocol"
)

const maxWorkHistoryTasks = 100

type workHistoryEntry struct {
	TaskID string `json:"task_id"`
	Text   string `json:"text"`
}

func (a *API) getWorkHistory(w http.ResponseWriter, r *http.Request) {
	for key := range r.URL.Query() {
		if key != "task_id" {
			writeError(w, invalid("invalid_query", "поддерживается только параметр task_id"))
			return
		}
	}
	ids := r.URL.Query()["task_id"]
	if len(ids) > maxWorkHistoryTasks {
		writeError(w, invalid("too_many_task_ids", "за один раз можно запросить не больше 100 этапов"))
		return
	}

	history := make([]workHistoryEntry, 0, len(ids))
	seen := make(map[string]struct{}, len(ids))
	for _, id := range ids {
		id = strings.TrimSpace(id)
		if id == "" || len(id) > 128 || strings.ContainsAny(id, "/\\\x00") {
			writeError(w, invalid("invalid_task_id", "task_id имеет недопустимый формат"))
			return
		}
		if _, duplicate := seen[id]; duplicate {
			continue
		}
		seen[id] = struct{}{}
		detail, err := a.store.Task(r.Context(), id)
		if errors.Is(err, ErrNotFound) {
			continue
		}
		if err != nil {
			writeError(w, err)
			return
		}
		history = append(history, workHistoryEntry{TaskID: id, Text: workHistoryText(detail.Task)})
	}
	writeJSON(w, http.StatusOK, map[string]any{"history": history})
}

// История сознательно не пересказывает result/error попытки: там могут быть
// логи, промпты и секреты. Экрану достаточно короткого человеческого итога.
func workHistoryText(task protocol.Task) string {
	switch task.State {
	case "queued", "pending", "created":
		return "Этап ждёт запуска"
	case "running", "preparing", "starting":
		return "Этап сейчас выполняется"
	case "succeeded":
		return "Этап успешно завершён"
	case "failed":
		return "Этап завершился ошибкой"
	case "cancelled":
		return "Этап отменён"
	default:
		return "Состояние этапа обновляется"
	}
}

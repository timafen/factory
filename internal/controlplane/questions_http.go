package controlplane

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

// Questions are pipeline stops that need the owner. The pilot writes them,
// the UI lists them and posts an answer; the pilot then resumes the pipeline.

var questionsMu sync.Mutex

func questionsDir() string {
	home := os.Getenv("FACTORY_DATA_HOME")
	if home == "" {
		home = "/opt/factory-data"
	}
	return filepath.Join(home, "pilot", "questions")
}

func (a *API) listQuestions(w http.ResponseWriter, r *http.Request) {
	questionsMu.Lock()
	defer questionsMu.Unlock()
	entries, err := os.ReadDir(questionsDir())
	if err != nil {
		if os.IsNotExist(err) {
			writeJSON(w, http.StatusOK, map[string]any{"questions": []any{}})
			return
		}
		writeError(w, unavailable(err))
		return
	}
	out := []map[string]any{}
	for _, e := range entries {
		if e.IsDir() || filepath.Ext(e.Name()) != ".json" {
			continue
		}
		data, err := os.ReadFile(filepath.Join(questionsDir(), e.Name()))
		if err != nil {
			continue
		}
		var rec map[string]any
		if err := json.Unmarshal(data, &rec); err != nil {
			continue
		}
		if questionContainsPythonMock(rec) {
			continue
		}
		// Admin records are an audit trail for an action the orchestrator already
		// attempted.  They are not questions for the owner unless explicitly
		// escalated after that attempt.
		if toString(rec["authority"]) == "admin" && rec["owner_only"] != true {
			continue
		}
		delete(rec, "prior_result") // large; not needed by the list UI
		out = append(out, rec)
	}
	sort.Slice(out, func(i, j int) bool {
		return toString(out[i]["id"]) < toString(out[j]["id"])
	})
	writeJSON(w, http.StatusOK, map[string]any{"questions": out})
}

func questionContainsPythonMock(rec map[string]any) bool {
	for _, field := range []string{"title", "situation", "question", "options", "answer", "escalation_reason"} {
		if value, ok := rec[field].(string); ok && isPythonMockRepr(value) {
			return true
		}
		if values, ok := rec[field].([]any); ok {
			for _, value := range values {
				if text, ok := value.(string); ok && isPythonMockRepr(text) {
					return true
				}
			}
		}
	}
	return false
}

func isPythonMockRepr(value string) bool {
	value = strings.TrimSpace(value)
	return (strings.HasPrefix(value, "<MagicMock ") || strings.HasPrefix(value, "<Mock ")) && strings.HasSuffix(value, ">")
}

func toString(v any) string {
	s, _ := v.(string)
	return s
}

type answerRequest struct {
	Answer string `json:"answer"`
}

func (a *API) answerQuestion(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("question_id")
	if !epicIDPattern.MatchString(id) {
		writeError(w, invalid("bad_question_id", "question id has an unexpected format"))
		return
	}
	var req answerRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, invalid("bad_body", "expected {\"answer\": \"...\"}"))
		return
	}
	if len(req.Answer) == 0 {
		writeError(w, invalid("empty_answer", "answer must not be empty"))
		return
	}
	questionsMu.Lock()
	defer questionsMu.Unlock()
	path := filepath.Join(questionsDir(), id+".json")
	data, err := os.ReadFile(path)
	if err != nil {
		writeError(w, ErrNotFound)
		return
	}
	var rec map[string]any
	if err := json.Unmarshal(data, &rec); err != nil {
		writeError(w, unavailable(err))
		return
	}
	rec["answer"] = req.Answer
	rec["status"] = "answered"
	rec["answered_by"] = "owner"
	rec["answered_at"] = a.store.now().UTC().Format(time.RFC3339)
	updated, err := json.MarshalIndent(rec, "", " ")
	if err != nil {
		writeError(w, unavailable(err))
		return
	}
	if err := os.WriteFile(path, updated, 0o644); err != nil {
		writeError(w, unavailable(err))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "status": "answered"})
}

func (a *API) dismissQuestion(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("question_id")
	if !epicIDPattern.MatchString(id) {
		writeError(w, invalid("bad_question_id", "question id has an unexpected format"))
		return
	}
	questionsMu.Lock()
	defer questionsMu.Unlock()
	if err := os.Remove(filepath.Join(questionsDir(), id+".json")); err != nil {
		writeError(w, ErrNotFound)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

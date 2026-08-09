package controlplane

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/owainlewis/factory/internal/protocol"
)

type fakeDialogRunner struct {
	calls    int
	brain    protocol.PilotBrain
	messages []protocol.DialogMessage
	answer   string
	err      error
}

func (f *fakeDialogRunner) Run(_ context.Context, brain protocol.PilotBrain, messages []protocol.DialogMessage) (string, error) {
	f.calls++
	f.brain = brain
	f.messages = append([]protocol.DialogMessage(nil), messages...)
	return f.answer, f.err
}

func dialogTestAPI(t *testing.T, runner dialogRunner) *API {
	t.Helper()
	path := filepath.Join(t.TempDir(), "pilot.json")
	body := `{"brain_chain":[{"cli":"codex","model":"first","provider":"openai","note":"Первая модель"},{"cli":"claude","model":"second","provider":"anthropic","note":"Вторая модель"}]}`
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	return &API{pilotConfig: NewPilotConfigStore(path), dialogRunner: runner}
}

func runDialogRequest(t *testing.T, api *API, body string) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(http.MethodPost, "/api/v1/dialog/messages", strings.NewReader(body))
	recorder := httptest.NewRecorder()
	api.postDialogMessage(recorder, request)
	return recorder
}

func TestDialogRunsSelectedModelWithOrderedHistory(t *testing.T) {
	runner := &fakeDialogRunner{answer: "Новый ответ"}
	api := dialogTestAPI(t, runner)
	recorder := runDialogRequest(t, api, `{"model":"second","messages":[{"role":"user","content":"Первый вопрос"},{"role":"assistant","content":"Первый ответ"},{"role":"user","content":"Второй вопрос"}]}`)
	if recorder.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body)
	}
	if runner.calls != 1 || runner.brain.CLI != "claude" || runner.brain.Model != "second" {
		t.Fatalf("wrong runner call: %#v", runner)
	}
	if len(runner.messages) != 3 || runner.messages[0].Content != "Первый вопрос" || runner.messages[2].Content != "Второй вопрос" {
		t.Fatalf("history changed: %#v", runner.messages)
	}
	var response protocol.DialogResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatal(err)
	}
	if response.ModelLabel != "Вторая модель" || response.Message.Content != "Новый ответ" {
		t.Fatalf("response=%#v", response)
	}
}

func TestDialogRejectsInvalidInputBeforeRunner(t *testing.T) {
	for name, body := range map[string]string{
		"unknown model": `{"model":"other","messages":[{"role":"user","content":"x"}]}`,
		"unknown role":  `{"model":"first","messages":[{"role":"system","content":"x"}]}`,
		"oversize":      `{"model":"first","messages":[{"role":"user","content":"` + strings.Repeat("x", dialogMaxBytes) + `"}]}`,
	} {
		t.Run(name, func(t *testing.T) {
			runner := &fakeDialogRunner{}
			recorder := runDialogRequest(t, dialogTestAPI(t, runner), body)
			if recorder.Code < 400 || runner.calls != 0 {
				t.Fatalf("status=%d calls=%d", recorder.Code, runner.calls)
			}
		})
	}
}

func TestDialogReturnsSafeRunnerErrors(t *testing.T) {
	for name, tc := range map[string]struct {
		runner *fakeDialogRunner
		status int
	}{
		"timeout": {&fakeDialogRunner{err: context.DeadlineExceeded}, http.StatusGatewayTimeout},
		"failure": {&fakeDialogRunner{err: errors.New("secret stderr")}, http.StatusBadGateway},
		"empty":   {&fakeDialogRunner{answer: "  "}, http.StatusBadGateway},
	} {
		t.Run(name, func(t *testing.T) {
			recorder := runDialogRequest(t, dialogTestAPI(t, tc.runner), `{"model":"first","messages":[{"role":"user","content":"x"}]}`)
			if recorder.Code != tc.status {
				t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body)
			}
			if strings.Contains(recorder.Body.String(), "secret stderr") {
				t.Fatal("runner error leaked")
			}
		})
	}
}

package controlplane

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

func TestHTTPServerWriteTimeoutCoversDialogTimeout(t *testing.T) {
	server := NewHTTPServer("127.0.0.1:0", http.NotFoundHandler())
	const responseReserve = 15 * time.Second
	minimum := server.ReadTimeout + dialogTimeout + responseReserve
	if server.WriteTimeout < minimum {
		t.Fatalf("WriteTimeout=%s must cover ReadTimeout=%s + dialog timeout=%s + reserve=%s", server.WriteTimeout, server.ReadTimeout, dialogTimeout, responseReserve)
	}
	if server.WriteTimeout != 90*time.Second {
		t.Fatalf("WriteTimeout=%s, want the agreed 90s budget", server.WriteTimeout)
	}
}

func TestHTTPServerDeliversDialogResponseAfterReadTimeoutWindow(t *testing.T) {
	if os.Getenv("FACTORY_LIVE_TIMEOUT_TEST") == "" {
		t.Skip("set FACTORY_LIVE_TIMEOUT_TEST=1 to run the 16-second live HTTP check")
	}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /dialog", func(w http.ResponseWriter, _ *http.Request) {
		time.Sleep(16 * time.Second)
		_, _ = io.WriteString(w, "long dialog response")
	})
	server := NewHTTPServer("127.0.0.1:0", mux)
	listener, err := net.Listen("tcp", server.Addr)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = server.Close() })
	go func() { _ = server.Serve(listener) }()

	response, err := http.Post("http://"+listener.Addr().String()+"/dialog", "application/json", strings.NewReader("{}"))
	if err != nil {
		t.Fatalf("dialog request failed after waiting beyond ReadTimeout: %v", err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatal(err)
	}
	if response.StatusCode != http.StatusOK || string(body) != "long dialog response" {
		t.Fatalf("status=%d body=%q", response.StatusCode, body)
	}
}

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
	body := `{"brain_chain":[{"cli":"codex","model":"same","provider":"openai","note":"Первая модель"},{"cli":"claude","model":"same","provider":"anthropic","note":"Вторая модель"}]}`
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
	recorder := runDialogRequest(t, api, `{"brain_index":1,"messages":[{"role":"user","content":"Первый вопрос"},{"role":"assistant","content":"Первый ответ"},{"role":"user","content":"Второй вопрос"}]}`)
	if recorder.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body)
	}
	if runner.calls != 1 || runner.brain.CLI != "claude" || runner.brain.Model != "same" {
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
		"unknown model": `{"brain_index":2,"messages":[{"role":"user","content":"x"}]}`,
		"unknown role":  `{"brain_index":0,"messages":[{"role":"system","content":"x"}]}`,
		"oversize":      `{"brain_index":0,"messages":[{"role":"user","content":"` + strings.Repeat("x", dialogMaxBytes+1) + `"}]}`,
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
		"timeout":    {&fakeDialogRunner{err: context.DeadlineExceeded}, http.StatusGatewayTimeout},
		"rate limit": {&fakeDialogRunner{err: errors.New("provider: rate limit exceeded")}, http.StatusTooManyRequests},
		"failure":    {&fakeDialogRunner{err: errors.New("secret stderr")}, http.StatusBadGateway},
		"empty":      {&fakeDialogRunner{answer: "  "}, http.StatusBadGateway},
	} {
		t.Run(name, func(t *testing.T) {
			recorder := runDialogRequest(t, dialogTestAPI(t, tc.runner), `{"brain_index":0,"messages":[{"role":"user","content":"x"}]}`)
			if recorder.Code != tc.status {
				t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body)
			}
			if strings.Contains(recorder.Body.String(), "secret stderr") {
				t.Fatal("runner error leaked")
			}
		})
	}
}

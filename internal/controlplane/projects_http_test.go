package controlplane

import (
	"bytes"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func projectHTTPServer(t *testing.T) *httptest.Server {
	t.Helper()
	store := newTestStore(t)
	return httptest.NewServer(NewHandler(store, slog.New(slog.NewTextHandler(io.Discard, nil))))
}

func postProjectJSON(t *testing.T, server *httptest.Server, body any) (*http.Response, []byte) {
	t.Helper()
	encoded, err := json.Marshal(body)
	if err != nil {
		t.Fatal(err)
	}
	request, err := http.NewRequest(http.MethodPost, server.URL+"/api/v1/projects", bytes.NewReader(encoded))
	if err != nil {
		t.Fatal(err)
	}
	request.Header.Set("Content-Type", "application/json")
	response, err := server.Client().Do(request)
	if err != nil {
		t.Fatal(err)
	}
	defer response.Body.Close()
	responseBody, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatal(err)
	}
	return response, responseBody
}

func TestProjectHTTPContractRejectsClientExecutorAndCommandFields(t *testing.T) {
	server := projectHTTPServer(t)
	defer server.Close()
	response, body := postProjectJSON(t, server, factoryProjectRequest())
	if response.StatusCode != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", response.StatusCode, body)
	}
	if !bytes.Contains(body, []byte(`"executor_group":"factory"`)) || bytes.Contains(body, []byte("super-secret-value")) {
		t.Fatalf("unsafe response: %s", body)
	}

	var raw map[string]any
	encoded, _ := json.Marshal(factoryProjectRequest())
	_ = json.Unmarshal(encoded, &raw)
	for _, field := range []string{"executor_group", "command"} {
		raw[field] = "root"
		response, body = postProjectJSON(t, server, raw)
		if response.StatusCode != http.StatusBadRequest || !strings.Contains(string(body), "malformed_json") {
			t.Fatalf("field %s accepted: status=%d body=%s", field, response.StatusCode, body)
		}
		delete(raw, field)
	}
}

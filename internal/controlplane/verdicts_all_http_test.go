package controlplane

import (
	"encoding/json"
	"net/http"
	"os"
	"path/filepath"
	"testing"
)

func TestHTTPVerdictsReturnsEveryReviewReturnReason(t *testing.T) {
	home := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", home)
	dir := filepath.Join(home, "pilot", "verdicts")
	if err := os.MkdirAll(dir, 0o700); err != nil {
		t.Fatal(err)
	}
	records := map[string]map[string]any{
		"review-new": {
			"task_id": "review-new", "stage": "Review", "action": "stop",
			"reason": "Нет проверки повторной оплаты", "verdict": "Длинное описание",
		},
		"review-old": {
			"task_id": "review-old", "stage": "Review", "action": "stop",
			"verdict": "Не учтён возврат без чека",
		},
		"review-pass": {
			"task_id": "review-pass", "stage": "Review", "action": "advance",
			"reason": "служебная причина", "verdict": "Работа принята",
		},
	}
	for name, record := range records {
		data, err := json.Marshal(record)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(dir, name+".json"), data, 0o600); err != nil {
			t.Fatal(err)
		}
	}

	fixture := newHTTPFixture(t)
	response := fixture.request(http.MethodGet, "/api/v1/verdicts", "", "", nil)
	requireStatus(t, response, http.StatusOK)
	body := decodeResponse[struct {
		Verdicts map[string]map[string]any `json:"verdicts"`
	}](t, response)

	if body.Verdicts["review-new"]["return_reason"] != "Нет проверки повторной оплаты" {
		t.Fatalf("new Review reason = %#v", body.Verdicts["review-new"])
	}
	if body.Verdicts["review-old"]["return_reason"] != "Не учтён возврат без чека" {
		t.Fatalf("old Review reason = %#v", body.Verdicts["review-old"])
	}
	if _, ok := body.Verdicts["review-pass"]["return_reason"]; ok {
		t.Fatalf("passing Review exposed return reason: %#v", body.Verdicts["review-pass"])
	}
	for id, verdict := range body.Verdicts {
		if _, ok := verdict["reason"]; ok {
			t.Fatalf("%s exposed generic reason: %#v", id, verdict)
		}
		if _, ok := verdict["verdict"]; ok {
			t.Fatalf("%s exposed long verdict: %#v", id, verdict)
		}
	}
}

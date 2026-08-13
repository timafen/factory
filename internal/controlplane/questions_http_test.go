package controlplane

import (
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestListQuestionsHidesPythonMockRepresentations(t *testing.T) {
	home := t.TempDir()
	t.Setenv("FACTORY_DATA_HOME", home)
	directory := filepath.Join(home, "pilot", "questions")
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	fixtures := map[string]string{
		"resolved.json": `{"id":"resolved","status":"resolved","title":"[auto] Исправить корзину","situation":"<MagicMock name='deep_diagnose().get()' id='140123456789'>","question":"<Mock name='deep_diagnose().get()' id='140123456790'>","options":["<MagicMock name='option' id='1'>"]}`,
		"open.json":     `{"id":"open","status":"open","title":"Проверить доставку","situation":"Заказ задерживается","question":"Продолжить проверку?","options":["Да","Нет"]}`,
		"topic.json":    `{"id":"topic","status":"open","title":"Обсудить MagicMock","situation":"Текст о MagicMock в тестах","question":"Почему MagicMock попал в тест?"}`,
		"admin.json":    `{"id":"admin","status":"resolved","authority":"admin","admin_action":{"scope":"staging","verb":"health"},"admin_result":"executed","machine_action":"wait","title":"Проверить стенд"}`,
	}
	for name, content := range fixtures {
		if err := os.WriteFile(filepath.Join(directory, name), []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}

	fixture := newHTTPFixture(t)
	response := fixture.request(http.MethodGet, "/api/v1/questions", "", "", nil)
	requireStatus(t, response, http.StatusOK)
	data, err := io.ReadAll(response.Body)
	response.Body.Close()
	if err != nil {
		t.Fatal(err)
	}
	body := string(data)
	if strings.Contains(body, "<MagicMock") || strings.Contains(body, "<Mock ") {
		t.Fatalf("response contains Python mock repr: %s", body)
	}
	var result struct {
		Questions []map[string]any `json:"questions"`
	}
	if err := json.Unmarshal([]byte(body), &result); err != nil {
		t.Fatal(err)
	}
	if len(result.Questions) != 2 {
		t.Fatalf("questions = %#v, want open question and MagicMock topic", result.Questions)
	}
	for _, question := range result.Questions {
		if question["id"] == "resolved" {
			t.Fatalf("resolved MagicMock question was returned: %#v", question)
		}
		if question["id"] == "admin" {
			t.Fatalf("admin audit was returned as an owner question: %#v", question)
		}
	}
	data, err = os.ReadFile(filepath.Join(directory, "resolved.json"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(data), "<MagicMock") {
		t.Fatal("resolved question was rewritten instead of filtered from the response")
	}
}

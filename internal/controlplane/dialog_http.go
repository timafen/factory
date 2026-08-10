package controlplane

import (
	"bytes"
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/owainlewis/factory/internal/protocol"
)

const (
	dialogMaxMessages        = 40
	dialogMaxBytes           = 64 << 10
	dialogMaxScreenshotBytes = 4 << 20
	dialogMaxRequestBytes    = 6 << 20
	dialogMaxOutput          = 1 << 20
	dialogTimeout            = 45 * time.Second
)

type dialogRunner interface {
	Run(context.Context, protocol.PilotBrain, []protocol.DialogMessage, string) (string, error)
}

type commandDialogRunner struct{}

func (commandDialogRunner) Run(ctx context.Context, brain protocol.PilotBrain, messages []protocol.DialogMessage, screenshotPath string) (string, error) {
	prompt := serializeDialog(messages)
	var command *exec.Cmd
	switch brain.CLI {
	case "codex":
		args := []string{"exec", "-m", brain.Model, "--skip-git-repo-check"}
		if screenshotPath != "" {
			args = append(args, "--image", screenshotPath)
		}
		command = exec.CommandContext(ctx, "codex", append(args, "-")...)
		command.Stdin = strings.NewReader(prompt)
	case "claude":
		if screenshotPath != "" {
			prompt += "\nК последнему вопросу приложен скриншот: " + screenshotPath + "\nПрочитай этот файл и учти изображение в ответе.\n"
		}
		command = exec.CommandContext(ctx, "claude", claudeDialogArgs(prompt, screenshotPath)...)
		command.Env = append(os.Environ(), "ANTHROPIC_MODEL="+brain.Model)
	default:
		return "", fmt.Errorf("unsupported dialog CLI")
	}
	command.Dir, _ = os.Getwd()
	var stdout bytes.Buffer
	command.Stdout = &limitedWriter{writer: &stdout, remaining: dialogMaxOutput}
	var stderr bytes.Buffer
	command.Stderr = &limitedWriter{writer: &stderr, remaining: dialogMaxOutput}
	if err := command.Run(); err != nil {
		return "", fmt.Errorf("dialog CLI failed: %w: %s", err, strings.TrimSpace(stderr.String()))
	}
	return strings.TrimSpace(stdout.String()), nil
}

func claudeDialogArgs(prompt, screenshotPath string) []string {
	args := []string{"-p", prompt, "--output-format", "text"}
	if screenshotPath != "" {
		args = append(args, "--add-dir", filepath.Dir(screenshotPath))
	}
	return args
}

type limitedWriter struct {
	writer    io.Writer
	remaining int
}

func (w *limitedWriter) Write(body []byte) (int, error) {
	original := len(body)
	if len(body) > w.remaining {
		body = body[:w.remaining]
	}
	if len(body) > 0 {
		_, _ = w.writer.Write(body)
		w.remaining -= len(body)
	}
	return original, nil
}

func serializeDialog(messages []protocol.DialogMessage) string {
	var b strings.Builder
	b.WriteString("Продолжи разговор. Ответь только на последний вопрос. Если нужно увидеть тестовый стенд глазами, используй factory-worker browser; он разрешает только https://staging-automation.tarser.net и его пути.\n\n")
	for _, message := range messages {
		label := "Пользователь"
		if message.Role == "assistant" {
			label = "Ассистент"
		}
		fmt.Fprintf(&b, "%s: %s\n", label, message.Content)
	}
	return b.String()
}

func (a *API) postDialogMessage(w http.ResponseWriter, r *http.Request) {
	if a.pilotConfig == nil || a.dialogRunner == nil {
		writeError(w, &ServiceError{Code: "dialog_unavailable", Message: "Диалог сейчас недоступен", Status: http.StatusServiceUnavailable})
		return
	}
	var request protocol.DialogRequest
	r.Body = http.MaxBytesReader(w, r.Body, dialogMaxRequestBytes)
	if !decodeJSON(w, r, &request) {
		return
	}
	if err := validateDialogRequest(request); err != nil {
		writeError(w, err)
		return
	}
	settings, err := a.pilotConfig.Read()
	if err != nil {
		writeError(w, err)
		return
	}
	var selected *protocol.PilotBrain
	if request.BrainIndex != nil && *request.BrainIndex >= 0 && *request.BrainIndex < len(settings.Settings.BrainChain) {
		selected = &settings.Settings.BrainChain[*request.BrainIndex]
	}
	if selected == nil || (selected.CLI != "codex" && selected.CLI != "claude") {
		writeError(w, invalid("unknown_dialog_model", "Выбранная модель недоступна"))
		return
	}
	if engineResting(selected.Model) {
		writeError(w, &ServiceError{Code: "dialog_rate_limited", Message: "У этой модели сейчас исчерпана квота. Выберите другую модель", Status: http.StatusTooManyRequests})
		return
	}
	if providerBlocked(selected.Provider) {
		writeError(w, &ServiceError{Code: "dialog_rate_limited", Message: "Подписка этой модели сейчас заблокирована. Выберите другую модель", Status: http.StatusTooManyRequests})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), dialogTimeout)
	defer cancel()
	screenshotPath, err := materializeDialogScreenshot(request.Screenshot)
	if err != nil {
		writeError(w, err)
		return
	}
	if screenshotPath != "" {
		defer os.RemoveAll(filepath.Dir(screenshotPath))
	}
	answer, err := a.dialogRunner.Run(ctx, *selected, request.Messages, screenshotPath)
	if err != nil {
		if errors.Is(ctx.Err(), context.DeadlineExceeded) || errors.Is(err, context.DeadlineExceeded) {
			writeError(w, &ServiceError{Code: "dialog_timeout", Message: "Модель не ответила вовремя. Попробуйте ещё раз", Status: http.StatusGatewayTimeout})
			return
		}
		if isDialogRateLimit(err) {
			writeError(w, &ServiceError{Code: "dialog_rate_limited", Message: "Лимит выбранной модели исчерпан. Попробуйте позже или выберите другую модель", Status: http.StatusTooManyRequests})
			return
		}
		writeError(w, &ServiceError{Code: "dialog_failed", Message: "Не удалось получить ответ модели. Попробуйте ещё раз", Status: http.StatusBadGateway})
		return
	}
	// Модель может ответить не отказом в ошибке, а текстом «твоя квота
	// кончилась». Это не ответ: говорим человеку правду и предлагаем другую.
	if isDialogQuotaText(answer) {
		writeError(w, &ServiceError{Code: "dialog_rate_limited", Message: "Лимит выбранной модели исчерпан. Выберите другую модель", Status: http.StatusTooManyRequests})
		return
	}
	if strings.TrimSpace(answer) == "" {
		writeError(w, &ServiceError{Code: "dialog_empty", Message: "Модель вернула пустой ответ. Попробуйте ещё раз", Status: http.StatusBadGateway})
		return
	}
	writeJSON(w, http.StatusOK, protocol.DialogResponse{Message: protocol.DialogMessage{Role: "assistant", Content: answer}, ModelLabel: dialogModelLabel(*selected)})
}

func materializeDialogScreenshot(screenshot *protocol.DialogScreenshot) (string, error) {
	if screenshot == nil {
		return "", nil
	}
	extensions := map[string]string{"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
	extension, ok := extensions[screenshot.ContentType]
	if !ok || strings.TrimSpace(screenshot.Name) == "" || screenshot.Data == "" {
		return "", invalid("invalid_dialog_screenshot", "Прикрепите PNG, JPEG или WebP")
	}
	data, err := base64.StdEncoding.Strict().DecodeString(screenshot.Data)
	if err != nil || len(data) == 0 || len(data) > dialogMaxScreenshotBytes {
		return "", invalid("invalid_dialog_screenshot", "Скриншот повреждён или превышает 4 МБ")
	}
	if detected := http.DetectContentType(data); detected != screenshot.ContentType {
		return "", invalid("invalid_dialog_screenshot", "Формат скриншота не совпадает с содержимым")
	}
	directory, err := os.MkdirTemp("", "factory-dialog-*")
	if err != nil {
		return "", fmt.Errorf("create dialog screenshot directory: %w", err)
	}
	path := filepath.Join(directory, "screenshot"+extension)
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		_ = os.RemoveAll(directory)
		return "", fmt.Errorf("create dialog screenshot: %w", err)
	}
	_, err = file.Write(data)
	closeErr := file.Close()
	if err != nil {
		_ = os.RemoveAll(directory)
		return "", fmt.Errorf("write dialog screenshot: %w", err)
	}
	if closeErr != nil {
		_ = os.RemoveAll(directory)
		return "", fmt.Errorf("close dialog screenshot: %w", closeErr)
	}
	return path, nil
}

func validateDialogRequest(request protocol.DialogRequest) error {
	if request.BrainIndex == nil || *request.BrainIndex < 0 || len(request.Messages) == 0 || len(request.Messages) > dialogMaxMessages {
		return invalid("invalid_dialog", "Проверьте модель и число сообщений")
	}
	total := 0
	for _, message := range request.Messages {
		if message.Role != "user" && message.Role != "assistant" {
			return invalid("invalid_dialog_role", "В истории есть неизвестная роль")
		}
		if strings.TrimSpace(message.Content) == "" {
			return invalid("invalid_dialog", "Сообщение не может быть пустым")
		}
		total += len(message.Content)
	}
	if request.Messages[len(request.Messages)-1].Role != "user" {
		return invalid("invalid_dialog", "Последним должен быть вопрос пользователя")
	}
	if total > dialogMaxBytes {
		return invalid("dialog_too_large", "История диалога слишком велика")
	}
	return nil
}

func isDialogRateLimit(err error) bool {
	message := strings.ToLower(err.Error())
	for _, marker := range []string{"rate limit", "rate_limit", "too many requests", "quota exceeded", "usage limit", "status 429", "error 429", "reached your", "usage-credits", "limit reached", "лимит исчерпан"} {
		if strings.Contains(message, marker) {
			return true
		}
	}
	return false
}

func isDialogQuotaText(answer string) bool {
	body := strings.ToLower(strings.TrimSpace(answer))
	if len(body) > 400 {
		return false
	}
	for _, marker := range []string{"reached your", "usage-credits", "usage limit", "limit reached", "лимит исчерпан"} {
		if strings.Contains(body, marker) {
			return true
		}
	}
	return false
}

func dialogModelLabel(brain protocol.PilotBrain) string {
	if strings.TrimSpace(brain.Note) != "" {
		return brain.Note
	}
	if strings.TrimSpace(brain.Provider) != "" {
		return brain.Provider + " — " + brain.Model
	}
	return "Выбранная модель — " + brain.Model
}

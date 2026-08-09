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
	dialogMaxMessages   = 40
	dialogMaxBytes      = 64 << 10
	dialogMaxOutput     = 1 << 20
	dialogMaxScreenshot = 4 << 20
	dialogTimeout       = 45 * time.Second
)

type dialogRunner interface {
	Run(context.Context, protocol.PilotBrain, []protocol.DialogMessage, *protocol.DialogScreenshot) (string, error)
}

type commandDialogRunner struct{}

func (commandDialogRunner) Run(ctx context.Context, brain protocol.PilotBrain, messages []protocol.DialogMessage, screenshot *protocol.DialogScreenshot) (string, error) {
	prompt := serializeDialog(messages)
	imagePath, err := materializeDialogScreenshot(screenshot)
	if err != nil {
		return "", err
	}
	if imagePath != "" {
		defer os.Remove(imagePath)
	}
	var command *exec.Cmd
	switch brain.CLI {
	case "codex":
		args := []string{"exec", "-m", brain.Model, "--skip-git-repo-check"}
		if imagePath != "" {
			args = append(args, "--image", imagePath)
		}
		command = exec.CommandContext(ctx, "codex", append(args, "-")...)
		command.Stdin = strings.NewReader(prompt)
	case "claude":
		if imagePath != "" {
			prompt += "\n\nК последнему вопросу приложен скриншот: " + imagePath + ". Открой его и учти в ответе."
		}
		command = exec.CommandContext(ctx, "claude", "-p", prompt, "--output-format", "text")
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

func materializeDialogScreenshot(screenshot *protocol.DialogScreenshot) (string, error) {
	if screenshot == nil {
		return "", nil
	}
	decoded, err := base64.StdEncoding.DecodeString(screenshot.Data)
	if err != nil || len(decoded) == 0 || len(decoded) > dialogMaxScreenshot {
		return "", errors.New("invalid screenshot")
	}
	extension := map[string]string{"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[screenshot.ContentType]
	if extension == "" {
		return "", errors.New("invalid screenshot")
	}
	file, err := os.CreateTemp("", "factory-dialog-*"+extension)
	if err != nil {
		return "", err
	}
	path := file.Name()
	if _, err = file.Write(decoded); err != nil {
		file.Close()
		os.Remove(path)
		return "", err
	}
	if err = file.Close(); err != nil {
		os.Remove(path)
		return "", err
	}
	return filepath.Clean(path), nil
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
	b.WriteString("Продолжи разговор. Ответь только на последний вопрос.\n\n")
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
	// The text conversation stays small, but a single screenshot is carried as
	// base64 JSON and needs its own bounded allowance.
	r.Body = http.MaxBytesReader(w, r.Body, int64(dialogMaxBytes+base64.StdEncoding.EncodedLen(dialogMaxScreenshot)+(4<<10)))
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
	answer, err := a.dialogRunner.Run(ctx, *selected, request.Messages, request.Screenshot)
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
	if request.Screenshot != nil {
		if _, err := base64.StdEncoding.DecodeString(request.Screenshot.Data); err != nil || request.Screenshot.Data == "" || len(request.Screenshot.Data) > base64.StdEncoding.EncodedLen(dialogMaxScreenshot) {
			return invalid("invalid_dialog_screenshot", "Скриншот должен быть изображением до 4 МБ")
		}
		if request.Screenshot.ContentType != "image/png" && request.Screenshot.ContentType != "image/jpeg" && request.Screenshot.ContentType != "image/webp" {
			return invalid("invalid_dialog_screenshot", "Поддерживаются PNG, JPEG и WebP")
		}
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

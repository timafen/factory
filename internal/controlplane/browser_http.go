package controlplane

import (
	"context"
	"encoding/base64"
	"net/http"
	"strings"
	"time"

	"github.com/owainlewis/factory/internal/serverbrowser"
)

type browserCapturer interface {
	Capture(context.Context, string) (serverbrowser.Capture, error)
}

func (a *API) captureBrowser(w http.ResponseWriter, r *http.Request) {
	var request struct {
		URL string `json:"url"`
	}
	if !decodeJSON(w, r, &request) {
		return
	}
	request.URL = strings.TrimSpace(request.URL)
	if _, err := serverbrowser.ValidateURL(request.URL); err != nil {
		writeError(w, invalid("browser_url_not_allowed", "Браузер открывает только основной тестовый стенд"))
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 45*time.Second)
	defer cancel()
	capture, err := a.browser.Capture(ctx, request.URL)
	if err != nil {
		writeError(w, &ServiceError{Code: "browser_unavailable", Message: "Не удалось открыть тестовый стенд в серверном браузере", Status: http.StatusBadGateway})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{
		"url": capture.URL, "content_type": "image/png", "data": base64.StdEncoding.EncodeToString(capture.PNG),
	})
}

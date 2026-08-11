# CARD-0080 — пауза карточки после resume и Origin за HTTPS-прокси

## HEAD

- Status: Implemented; ready for Verify.
- Branch: `factory/9544acc4-6eb-0c2cd660-356`
- Implementation commit: `833ec02301b10d7958d4e15aa48133ad7c08f769` — настоящий TLS reverse proxy и browser-доказательство resume.
- What changed: browser fixture запускает HTTPS reverse proxy перед branch build/API, очищает поддельные forwarded-заголовки и передаёт единственный loopback origin.
- What changed: Playwright подтверждает resume, очистку stale pause у completed pipeline, отсутствие `stopped` на completed и безопасный русский повтор; есть desktop/390px snapshots.
- Evidence: `FACTORY_BROWSER_LAUNCHER=/missing npx playwright test -g 'resumes a paused pipeline through the real HTTPS proxy and keeps Origin protected'` → PASS (1 passed, 51.5s); `go test ./...` → PASS; `npm test && npm run lint && npm run build && git diff --exit-code -- dist` → PASS.
- Snapshots: `web/test-results/screenshots/pause-resume-https-desktop.png`; `web/test-results/screenshots/pause-resume-https-phone.png` (регенерируются сценарием, runtime artifacts не коммитятся).
- Next action: Verify запустить полный browser suite в целевом sandbox.

## LOG

### 2026-08-11 — Implement

- Защищены forwarded host/proto: только loopback, одиночные согласованные web-значения; добавлена точная regression-проверка `127.0.0.1:7337` → body validation 400, не Origin 403.
- Resume очищает pause после принятой queued task и для completed-конфликта; повтор использует ту же задачу, ошибка записи сохраняет pause.
- UI скрывает внутренние API-сообщения и показывает русское объяснение с доступной кнопкой повтора.
- Проверено targeted Go, web unit и production build; внешний HTTPS Playwright не запускался в этой среде.

### 2026-08-11 — Implement

- Добавлен воспроизводимый TLS reverse proxy перед e2e branch build/API: он удаляет supplied `Forwarded`/`X-Forwarded-*` и сам ставит согласованные `X-Forwarded-Host`/`Proto`.
- Новый Playwright fixture создаёт paused и completed pipeline, проверяет HTTPS resume, stale pause cleanup, русский retry и запрет чужого Origin со spoofed forwarding на 1440px и 390px.
- `FACTORY_BROWSER_LAUNCHER=/missing npx playwright test -g 'resumes a paused pipeline through the real HTTPS proxy and keeps Origin protected'` → PASS; snapshots сохранены в `web/test-results/screenshots/pause-resume-https-{desktop,phone}.png`.

# CARD-0080 — пауза карточки после resume и Origin за HTTPS-прокси

## HEAD

- Status: Implemented; ready for Review.
- Branch: `factory/dc51eda4-83e-b463b62a-297`
- Implementation commit: `17e98219cb7170c940b62bb5dbb808d45aefc447` — исправление Origin, resume state и безопасной ошибки UI.
- What changed: доверенный loopback proxy принимает согласованный HTTPS Origin; повторный resume идемпотентен, очищает pause и не оставляет completed pipeline в `stopped_owner`. UI показывает русское безопасное объяснение с повтором.
- Evidence: `go test ./internal/controlplane -run 'TestPrepareMutation|TestResumePausedWork'` → PASS; web unit 14/14 и build → PASS.
- Next action: Review проверить внешний HTTPS Playwright сценарий на desktop и 390px.

## LOG

### 2026-08-11 — Implement

- Защищены forwarded host/proto: только loopback, одиночные согласованные web-значения; добавлена точная regression-проверка `127.0.0.1:7337` → body validation 400, не Origin 403.
- Resume очищает pause после принятой queued task и для completed-конфликта; повтор использует ту же задачу, ошибка записи сохраняет pause.
- UI скрывает внутренние API-сообщения и показывает русское объяснение с доступной кнопкой повтора.
- Проверено targeted Go, web unit и production build; внешний HTTPS Playwright не запускался в этой среде.

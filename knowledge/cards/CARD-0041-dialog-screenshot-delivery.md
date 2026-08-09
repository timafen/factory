# CARD-0041 — Скриншот в вопросе диалога

## HEAD

- Status: Implemented, ready for Review
- Branch: `factory/3fe4740d-52e-6db7d063-54f`
- Head commit: `b5213e6`
- What changed: диалог принимает PNG/JPEG/WebP до 4 МБ, показывает предпросмотр и передаёт снимок выбранной модели.
- What changed: после успешной отправки браузер очищает выбор, а сервер всегда удаляет временный файл после вызова модели.
- Evidence: `go test ./...` → PASS; `npm test` → PASS.
- Evidence: `npx tsc -p tsconfig.app.json --noEmit` and `npm run build` → PASS.
- Next action: проверить экран и контракт на Review.

## LOG

### 2026-08-09 — Implement

Работа заново собрана на свежем `origin/main` полным изолированным набором. Дополнительно закреплён отказ для корректного по сигнатуре PNG, который превышает лимит на один байт. Целевые проверки и финальные полные наборы `go test ./...` и `npm test`, TypeScript-проверка и production-сборка прошли.

### 2026-08-09 — Implement

Собран сквозной контракт снимка от React-формы до CLI модели. Сервер проверяет base64, MIME, сигнатуру и лимит 4 МБ; тест доказывает доступность файла во время вызова и удаление после него. Клиентские тесты покрывают предпросмотр, сериализацию, очистку после успеха и сброс старого снимка при неверном новом файле. Финальная проверка: все Go-пакеты и 103 Vitest-теста прошли, TypeScript и production-сборка успешны.

ГОТОВО-КОГДА: файл `internal/controlplane/dialog_http.go`
ГОТОВО-КОГДА: файл `web/src/Dialog.tsx`
ГОТОВО-КОГДА: команда `go test ./internal/controlplane ./internal/protocol`
ГОТОВО-КОГДА: команда `cd web && npx vitest run src/Dialog.test.tsx && npx tsc -p tsconfig.app.json --noEmit && npm run build`

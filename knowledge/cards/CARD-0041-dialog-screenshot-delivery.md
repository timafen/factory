# CARD-0041 — Скриншот в вопросе диалога

## HEAD

- Status: Implemented, awaiting review
- Branch: `factory/0631be53-60c-b213b0f3-49d`
- Head commit: `ba96e29`
- What changed: диалог показывает выбранный скриншот и отправляет его вместе с вопросом; сервер проверяет изображение, передаёт его выбранной модели и удаляет временный файл.
- Evidence: `npm run typecheck` and `npm run lint` → exit 0; `npm test -- --run` → 102 passed; `npm run build` → built; `go test ./...` → passed.
- Next action: открыть `/dialog` на стенде и проверить вопрос с приложенным скриншотом.

ГОТОВО-КОГДА: файл `web/src/Dialog.tsx`
ГОТОВО-КОГДА: файл `web/src/api.ts`
ГОТОВО-КОГДА: файл `web/src/types.ts`
ГОТОВО-КОГДА: файл `internal/protocol/types.go`
ГОТОВО-КОГДА: файл `internal/controlplane/dialog_http.go`
ГОТОВО-КОГДА: файл `internal/controlplane/dialog_http_test.go`
ГОТОВО-КОГДА: файл `web/src/Dialog.test.tsx`
ГОТОВО-КОГДА: команда `cd web && npx tsc -p tsconfig.app.json --noEmit`
ГОТОВО-КОГДА: команда `cd web && npm test -- --run src/Dialog.test.tsx --reporter=verbose`
ГОТОВО-КОГДА: команда `go test ./internal/controlplane -run 'TestDialog(DeliversScreenshot|RejectsInvalidScreenshot)' -count=1 -v`

## LOG

### 2026-08-09 — Implement

Реализован единый путь скриншота от выбора и предпросмотра в диалоге до проверенного временного файла у запускаемой модели. Ограничение — 4 МБ, разрешены PNG, JPEG и WebP; временный файл удаляется после любого результата модели. Клиентский TypeScript, четыре теста диалога и целевые серверные тесты прошли.

### 2026-08-09 — Implement

Реализация заново собрана на свежем `origin/main` без посторонних файлов. Полностью прошли `go test ./...`, 102 web-теста, TypeScript, ESLint и production-сборка; код реализации после перебазирования зафиксирован коммитом `ba96e29`.

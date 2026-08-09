# CARD-0041 — Скриншот в вопросе диалога

## HEAD

- Status: Implemented, awaiting repeat review
- Branch: `factory/a024e3f1-5d1-d904413b-989`
- Head commit: `d3bc401`
- What changed: Claude получает доступ к каталогу временного скриншота через `--add-dir`; интерфейс ждёт чтения последнего выбранного файла и не отправляет устаревший снимок.
- Evidence: целевые Go-тесты → passed; `npx tsc -p tsconfig.app.json --noEmit` → exit 0; `npm test -- --run src/Dialog.test.tsx --reporter=verbose` → 5 passed.
- Next action: провести повторную проверку двух закрытых замечаний.

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

### 2026-08-09 — Implement

После замечаний ревью Claude разрешён каталог временного скриншота через `--add-dir`, а отправка вопроса блокируется до чтения последнего выбранного файла; устаревший `FileReader` больше не меняет предпросмотр. Целевые Go-тесты, пять тестов диалога и обязательная компиляция TypeScript прошли.

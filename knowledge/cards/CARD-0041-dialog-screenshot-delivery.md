# CARD-0041 — Скриншот в вопросе диалога

## HEAD

- Status: Implemented, awaiting repeat review
- Branch: `factory/1c4b7bf8-3d2-2742f535-256`
- Head commit: `2856d62`
- What changed: скриншот создаётся в отдельном временном каталоге; Claude получает через `--add-dir` только этот каталог, который целиком удаляется после ответа.
- Evidence: регрессионный Go-тест изоляции → passed; пакеты `controlplane`, `worker`, `protocol` → passed; 5 web-тестов, TypeScript и production-сборка → passed.
- Next action: повторно проверить реализацию на Review.

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

### 2026-08-09 — Implement

Закрыта утечка границ доступа: для снимка создаётся отдельный каталог, Claude получает только его, а `defer os.RemoveAll` удаляет каталог целиком. Регрессионный тест подтверждает, что системный `/tmp` не передаётся и посторонний временный файл недоступен; затронутые Go-пакеты, пять web-тестов, TypeScript и production-сборка прошли.

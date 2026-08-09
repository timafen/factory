# CARD-0041 — Скриншот в вопросе диалога

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/daedd382-fd2-58251dc1-60c`
- Head commit: `a45bbd2`
- What changed: диалог принимает PNG, JPEG или WebP до 4 МБ, показывает предпросмотр и передаёт снимок выбранной модели; файл изолирован и удаляется после ответа.
- Evidence: `go test ./...` → passed; 106 web-тестов, TypeScript, ESLint и production-сборка → passed; целевые серверные и UI-тесты → passed; живые Claude и Codex с PNG ответили «получен».
- Next action: человеку проверить карточку и влить ветку.

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

### 2026-08-09 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Пользователь выбирает PNG/JPEG/WebP до 4 МБ, видит предпросмотр и отправляет байты | `npm test -- --run src/Dialog.test.tsx --reporter=verbose` | 5/5 passed: предпросмотр, отправка и ожидание последнего выбора подтверждены; UI ограничивает MIME и размер. |
| Сервер принимает только допустимый снимок и передаёт его модели | `go test ./internal/controlplane -run 'TestDialog(DeliversScreenshot|RejectsInvalidScreenshot)' -count=1 -v` | passed: байты доставлены; неизвестный MIME, битая Base64 и несовпадение содержимого отклонены. |
| Временный файл не оставляет данных и Claude видит только его каталог | тот же Go-тест и живой `claude -p … --add-dir <isolated-dir>` | passed: каталог удалён; CLI получил PNG и ответил «получен». |
| Codex получает изображение | живой `codex exec … --image <png>` | passed: CLI получил PNG и ответил «получен». |
| Смежные интерфейс и сборка не регрессировали | `go test ./...`; `npm test`; `npm run typecheck`; `npm run lint`; `npm run build` | passed: Go-набор, 106 web-тестов, типы, lint и production-сборка. |

Неблокирующая находка: при ошибке `FileReader` поле выбора не сбрасывается, поэтому повторный выбор того же файла может не вызвать `change`; основной сценарий не затронут.

### 2026-08-09 — Implement

Реализован единый путь скриншота от выбора и предпросмотра в диалоге до проверенного временного файла у запускаемой модели. Ограничение — 4 МБ, разрешены PNG, JPEG и WebP; временный файл удаляется после любого результата модели. Клиентский TypeScript, четыре теста диалога и целевые серверные тесты прошли.

### 2026-08-09 — Implement

Реализация заново собрана на свежем `origin/main` без посторонних файлов. Полностью прошли `go test ./...`, 102 web-теста, TypeScript, ESLint и production-сборка; код реализации после перебазирования зафиксирован коммитом `ba96e29`.

### 2026-08-09 — Implement

После замечаний ревью Claude разрешён каталог временного скриншота через `--add-dir`, а отправка вопроса блокируется до чтения последнего выбранного файла; устаревший `FileReader` больше не меняет предпросмотр. Целевые Go-тесты, пять тестов диалога и обязательная компиляция TypeScript прошли.

### 2026-08-09 — Implement

Закрыта утечка границ доступа: для снимка создаётся отдельный каталог, Claude получает только его, а `defer os.RemoveAll` удаляет каталог целиком. Регрессионный тест подтверждает, что системный `/tmp` не передаётся и посторонний временный файл недоступен; затронутые Go-пакеты, пять web-тестов, TypeScript и production-сборка прошли.

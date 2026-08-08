# Infrastructure findings backlog

### 2026-08-08 — Экран настроек pilot
На ветке `factory/ddaa8de1-fa2-66c96daa-db5` (проверенный HEAD `b279e48`) добавлены безопасный API и `/settings` для `pilot/config.json`.
Список worker ID впервые берётся из уже известных control-plane исполнителей и дальше хранится в настройках; default остаётся `allow_any_worker=true`.
Доказательство: `go test ./...`, `npm test`, `npm run lint`, `npm run build` (результаты зафиксированы в delivery report).
Открытый риск: pilot не участвует в общем межпроцессном lock; конфликт API определяется по версии непосредственно перед atomic replace.

## HEAD
READY: замечания проверки экрана Settings исправлены. Branch: `factory/7ce70e06-806-c495dda7-644`. Head commit: `5d49ada` (последний содержательный коммит; вершина ветки — служебная правка только этой карточки).
What changed: поле заметки показывается и сохраняется даже при отсутствии `_note` в ответе API; факты исходной реализации исправлены на branch `factory/ddaa8de1-fa2-66c96daa-db5`, HEAD `b279e48`.
Evidence: `go test ./...`, `go build ./...`, Vitest (75), ESLint, TypeScript/Vite build — PASS; Playwright — 18 passed.
Next action: повторно проверить поставку с правилом приёмки служебного коммита карточки.

## LOG

### 2026-08-08 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Экран Settings показывает конфигурацию | `npx playwright test -g 'edits pilot settings from the Settings screen'` | PASS: открыт `/settings`, видны Pilot settings и Brain chain |
| Изменение сохраняется | тот же Playwright-сценарий | PASS: PUT успешен, `poll_seconds` изменён с 10 на 15 и сохранён после reload |
| Некорректная политика worker отклоняется | `go test ./...` (`TestPilotConfigValidationWorkerPolicy`) и `npm test -- --run` | PASS: строгий неизвестный worker отклонён, UI блокирует сохранение |
| Устаревшая версия не перезаписывает файл | `go test ./...` (`TestPilotConfigStorePreservesNotesAndRejectsConflict`) | PASS: conflict отклонён, содержимое файла не изменено |
| Регрессии смежного UI | `npm run test:browser` | BLOCKED: Workers E2E не нашёл `Implement the modern control-plane UI` на `control-plane.spec.ts:563` |

### 2026-08-08 — Implement

Падение Workers оказалось временной гонкой фикстуры: 30-секундные online-окно worker и lease активной попытки истекали во время последовательного suite. Тест поддерживает lease до своего запуска и посылает свежую регистрацию `Build Mac` перед открытием `/workers`. Полный `npm run test:browser` прошёл: 18/18; Go tests/build и frontend test/lint/typecheck/build также прошли.

### 2026-08-08 — Implement

Поле Configuration note теперь всегда видно и позволяет создать отсутствующий `_note`; регрессионный Vitest проверяет пустое поле и отправку новой заметки. Исправлены фактические branch/HEAD исходной реализации. Доказательство: `go test ./...`, `go build ./...`, `npm test -- --run` (75), `npm run lint`, `npm run typecheck`, `npm run build` и `npm run test:browser` (18) — PASS.

### 2026-08-08 — Implement

В HEAD записан последний содержательный коммит `5d49ada`. Верхний коммит поставки является служебной правкой только этой карточки; при проверке HEAD допустим как родитель вершины ветки. Содержательная реализация и результаты её проверок не изменялись.

### 2026-08-08 — Известные регрессии проверок экрана «Работа»
На ветке `factory/15b971af-c84-e1765036-dbe` предметные Vitest-тесты (7/7), typecheck и production build прошли; релиз `a721b1f` ранее прошёл штатный health-check.
Полный Vitest имеет 15 известных падений в неизменённом `App.test.tsx`, а Playwright ожидает устаревший английский заголовок `Factory overview` вместо «Главное»; по решению владельца они не входят в этап.
Дополнительно текущий `go test ./...` не компилирует неизменённый `internal/controlplane/pilot_config_test.go` из-за рассинхронизации типа `PilotConfig.Stages`; предметный код карточки 0031 это не затрагивает.
Риск: общие наборы останутся красными до отдельных исправлений тестовой инфраструктуры.

### 2026-08-08 — Русские пояснения на экране настроек
На ветке `factory/4c93386d-e8f-fb980c00-976` все поля `/settings` получили русские названия и видимые пояснения; обновлены тесты доступных подписей и сохранения.
Доказательство: Settings Vitest 4/4, ESLint изменённых файлов, typecheck, production build и `go build ./...` — PASS.
Открытый риск: общие Vitest и Go tests сохраняют ранее зафиксированные несвязанные падения в `App.test.tsx` и `pilot_config_test.go`.

### 2026-08-08 — Экран настроек выделен в чистую поставку
На ветке `factory/b2ac3700-bbb-471a9799-086` локализация `/settings`, её тест и эта запись перенесены поверх свежего `origin/main` без изменений экранов «Работа» и навигации.
Доказательство: Settings Vitest 4/4, ESLint двух изменённых TSX-файлов, `tsc -p tsconfig.app.json --noEmit` и production build — PASS; diff относительно `origin/main` содержит только три разрешённых файла.
Открытый риск: полный Vitest сохраняет 15 падений в неизменённом `App.test.tsx`, общий lint — ошибки в неизменённых файлах; они вне узкой поставки по решению владельца.

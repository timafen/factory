# Infrastructure findings backlog

### 2026-08-08 — Экран настроек pilot
На ветке `factory/ddaa8de1-fa2-66c96daa-db5` (проверенный HEAD `b279e48`) добавлены безопасный API и `/settings` для `pilot/config.json`.
Список worker ID впервые берётся из уже известных control-plane исполнителей и дальше хранится в настройках; default остаётся `allow_any_worker=true`.
Доказательство: `go test ./...`, `npm test`, `npm run lint`, `npm run build` (результаты зафиксированы в delivery report).
Открытый риск: pilot не участвует в общем межпроцессном lock; конфликт API определяется по версии непосредственно перед atomic replace.

## HEAD
Status: READY — экран «Обзор» пересобран чисто от актуального `origin/main`.
Branch: `factory/35b1cddd-88e-f65eeedb-184`.
Head commit: `25218e1` (содержательная вершина перед служебным коммитом карточки).
What changed: активная работа показывает очищенное название, постановщика и локализованный этап; API считает фактические элементы `running`.
Evidence: `go test ./...`; Overview Vitest 5/5; TypeScript; production build; ESLint изменённых файлов — PASS. Общий ESLint: 10 прежних ошибок вне diff.
Scope: `git diff origin/main...25218e1` — ровно 6 файлов реализации, тестов и собранного интерфейса.
Next action: проверить экран `/` и принять чистую поставку.

## LOG

### 2026-08-08 — Implement

Ветка заново отведена от `origin/main` (`406f985`), перенесён только содержательный коммит экрана «Обзор»; diff содержит 6 целевых файлов. `go test ./...`, `npx vitest run src/Overview.test.tsx`, `npx tsc -p tsconfig.app.json --noEmit`, `npm run build` и ESLint изменённых файлов прошли. Общий `npm run lint` остаётся красным на 10 существовавших ошибках в несвязанных файлах; открытый риск ограничен этим базовым долгом.

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

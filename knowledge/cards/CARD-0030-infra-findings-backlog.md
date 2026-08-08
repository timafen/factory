# Infrastructure findings backlog

### 2026-08-08 — Экран настроек pilot
На ветке `factory/ddaa8de1-fa2-66c96daa-db5` (проверенный HEAD `b279e48`) добавлены безопасный API и `/settings` для `pilot/config.json`.
Список worker ID впервые берётся из уже известных control-plane исполнителей и дальше хранится в настройках; default остаётся `allow_any_worker=true`.
Доказательство: `go test ./...`, `npm test`, `npm run lint`, `npm run build` (результаты зафиксированы в delivery report).
Открытый риск: pilot не участвует в общем межпроцессном lock; конфликт API определяется по версии непосредственно перед atomic replace.

## HEAD
- Status: READY — данные активной работы сохраняются при сетевом отказе метаданных.
- Branch: `factory/c27c6f88-465-5fb6cfc7-9bb`.
- Head commit: `69af0d4` (содержательная реализация; следующий коммит обновляет только карточку).
- What changed: dashboard и `/api/v1/works` обрабатываются независимо; при rejected `/works` экран показывает dashboard и предупреждает о неполных сведениях.
- Evidence: `npx tsc -p tsconfig.app.json --noEmit`, Vitest 6/6, `npm run build` — PASS; lint блокируют прежние ошибки вне изменения.
- One next action: Review повторно проверяет только сетевой отказ `/api/v1/works`.

## LOG

### 2026-08-08 — Implement

`Promise.all` заменён на независимую обработку результатов через `Promise.allSettled`: успешный `/api/v1/dashboard` больше не теряется при rejected fetch `/api/v1/works`, а интерфейс показывает предупреждение о неполных сведениях. Регрессионный тест моделирует именно `TypeError` сетевого запроса. Доказательство: TypeScript — PASS, `Overview.test.tsx` — 6/6 PASS, Vite build — PASS. Общий lint остаётся красным на прежних ошибках, включая старый вызов `pull()` в `useEffect`.

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

### 2026-08-08 — Implement

Исправлен факт предыдущей проверки: фактическая ветка — `factory/12e435b3-159-6232b71f-58e`, её HEAD — `5e19a03` (не `942ca18`). Техзадание для повторного Review дословно:

- major — `web/src/Overview.tsx:30`: этап извлекается из свободного текста заголовка, а не передаётся структурированными данными. Обычная задача показывает «Этап: не указан», а вручную заданный заголовок может показать произвольный этап. Это не гарантирует требование «на каком этапе». Исправление: хранить/выдавать этап в API метаданных и отображать его без парсинга title; добавить серверный и UI-тесты.
- minor — `knowledge/cards/CARD-0030-infra-findings-backlog.md:12`: HEAD указан как `942ca18`, хотя фактический HEAD проверяемой ветки — `5e19a03`; запись в LOG также ссылается на другую ветку. Исправить карточку, чтобы она была достоверной.

Реализация: API отдаёт `stage` из сохранённого `workflow_title`, UI показывает только это поле; добавлены серверный и UI-тесты. Доказательство: `go test ./...`, Go build, `TestWorksReturnsStructuredStageFromTaskWorkflow`, Vitest 5/5, TypeScript/Vite build — PASS.

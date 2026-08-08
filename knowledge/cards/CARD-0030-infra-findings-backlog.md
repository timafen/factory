# Infrastructure findings backlog

### 2026-08-08 — Экран настроек pilot
На ветке `factory/16f498d1-b11-e78d8f37-f17` добавлены безопасный API и `/settings` для `pilot/config.json`.
Список worker ID впервые берётся из уже известных control-plane исполнителей и дальше хранится в настройках; default остаётся `allow_any_worker=true`.
Доказательство: `go test ./...`, `npm test`, `npm run lint`, `npm run build` (результаты зафиксированы в delivery report).
Открытый риск: pilot не участвует в общем межпроцессном lock; конфликт API определяется по версии непосредственно перед atomic replace.

## HEAD
READY: экран Settings и смежный Workers E2E проходят полностью. Branch: `factory/ddaa8de1-fa2-66c96daa-db5`. Head commit: `d39ae6e`.
What changed: Workers-фикстура поддерживает lease синтетической активной задачи и обновляет регистрацию worker непосредственно перед проверкой экрана.
Evidence: `npm run test:browser` — 18 passed; `go test ./...`, Go build, Vitest (74 tests), ESLint, TypeScript и Vite build — PASS.
Next action: открыть `/settings` в среде проекта и принять изменение.

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

### 2026-08-08 — Implement: активная работа на экране «Обзор»

На ветке `factory/7e647a69-c2d-ea37d437-4ba` экран «Обзор» показывает активные работы, тип постановщика и текущий этап по данным `/api/v1/dashboard` и `/api/v1/works`. Проверено: Vitest 78/78, Playwright 18/18, TypeScript и ESLint без ошибок, Vite build и `go test ./web/...` прошли. Открытый риск: постановщик сопоставляется по названию работы, поэтому одинаковые названия могут столкнуться; API не раскрывает имя человека.

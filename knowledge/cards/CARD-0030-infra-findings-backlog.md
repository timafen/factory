# Infrastructure findings backlog

### 2026-08-08 — Экран настроек pilot
На ветке `factory/16f498d1-b11-e78d8f37-f17` добавлены безопасный API и `/settings` для `pilot/config.json`.
Список worker ID впервые берётся из уже известных control-plane исполнителей и дальше хранится в настройках; default остаётся `allow_any_worker=true`.
Доказательство: `go test ./...`, `npm test`, `npm run lint`, `npm run build` (результаты зафиксированы в delivery report).
Открытый риск: pilot не участвует в общем межпроцессном lock; конфликт API определяется по версии непосредственно перед atomic replace.

## HEAD
- Status: READY — экран «Обзор» показывает активную работу, постановщика и этап.
- Branch: `factory/12e435b3-159-6232b71f-58e`
- Head commit: `942ca18`
- Что изменилось: постановщик назван согласованной ролью — «поставил владелец»
  или «поставила Фабрика (управляющий)»; имя отдельно не хранится.
- Evidence: Vitest 79/79, точечный Playwright 1/1, ESLint, Vite, Go build и
  `go test ./...` — PASS.
- One next action: открыть `/` и проверить блок «Сейчас в работе».

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

На ветке `factory/e712fd10-583-e7dc7c9c-857` экран «Обзор» показывает активные работы, постановщика и этап из реальных `/api/v1/dashboard` и `/api/v1/works`; метаданные связаны по стабильному ID. Проверено: Go suite/build, Vitest 79/79, TypeScript, ESLint, Vite build и Playwright обзора прошли. Открытое ограничение: сервер различает владельца и оркестратор automation, но не хранит имя конкретного человека.

### 2026-08-08 — Implement

По решению владельца критерий «кем поставлено» реализован ролью без отдельного
имени: экран пишет «поставил владелец» или «поставила Фабрика (управляющий)».
Настройки не входят в diff относительно `main`. Vitest 79/79, точечный Playwright
1/1, ESLint, production-сборка UI, Go build и `go test ./...` прошли.

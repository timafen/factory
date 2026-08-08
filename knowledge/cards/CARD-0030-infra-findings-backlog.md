# Infrastructure findings backlog

### 2026-08-08 — Экран настроек pilot
На ветке `factory/16f498d1-b11-e78d8f37-f17` добавлены безопасный API и `/settings` для `pilot/config.json`.
Список worker ID впервые берётся из уже известных control-plane исполнителей и дальше хранится в настройках; default остаётся `allow_any_worker=true`.
Доказательство: `go test ./...`, `npm test`, `npm run lint`, `npm run build` (результаты зафиксированы в delivery report).
Открытый риск: pilot не участвует в общем межпроцессном lock; конфликт API определяется по версии непосредственно перед atomic replace.

## HEAD
BLOCKED: полный браузерный прогон имеет сбой в несвязанном сценарии Workers; новая проверка Settings изолированно проходит. Branch: `factory/16f498d1-b11-e78d8f37-f17`. Head commit: `ddd5f87`.
Evidence: `go test ./...`, сборка `go build ./cmd/factory-server`, Vitest, ESLint, TypeScript и Vite прошли; HTTP-тесты проверили сохранение, валидацию и conflict; изолированный Playwright-сценарий Settings сохранил `poll_seconds=15` после перезагрузки.
Next action: выяснить и устранить сбой E2E Workers, затем повторить полный `npm run test:browser`.

## LOG

### 2026-08-08 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Экран Settings показывает конфигурацию | `npx playwright test -g 'edits pilot settings from the Settings screen'` | PASS: открыт `/settings`, видны Pilot settings и Brain chain |
| Изменение сохраняется | тот же Playwright-сценарий | PASS: PUT успешен, `poll_seconds` изменён с 10 на 15 и сохранён после reload |
| Некорректная политика worker отклоняется | `go test ./...` (`TestPilotConfigValidationWorkerPolicy`) и `npm test -- --run` | PASS: строгий неизвестный worker отклонён, UI блокирует сохранение |
| Устаревшая версия не перезаписывает файл | `go test ./...` (`TestPilotConfigStorePreservesNotesAndRejectsConflict`) | PASS: conflict отклонён, содержимое файла не изменено |
| Регрессии смежного UI | `npm run test:browser` | BLOCKED: Workers E2E не нашёл `Implement the modern control-plane UI` на `control-plane.spec.ts:563` |

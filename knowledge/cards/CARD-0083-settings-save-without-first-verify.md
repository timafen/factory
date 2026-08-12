Implementation commit: ad763c7993aa2cdd52d18d96bd1d41078bccaab2 — E2E подтверждает единственность кнопки сохранения настроек

# CARD-0083 — Сохранение настроек без `.first()`

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/4308bd41-51a-d8fb5527-795`.
- Implementation commit: `ad763c7993aa2cdd52d18d96bd1d41078bccaab2` — E2E подтверждает единственность кнопки сохранения настроек.
- What changed: сценарий `/settings` находит кнопку строго внутри `.settings-page`, проверяет ровно один результат и нажимает его без `.first()`.
- Evidence: `npx tsc -p tsconfig.app.json --noEmit` PASS; 158 unit tests PASS; 21 Playwright tests PASS, including the settings-save scenario; pinned diff contains only this card and the target E2E file.
- One next action: human merge into `main`.

## LOG

### 2026-08-12 — Implement

После замечания Verify сценарий сохранения получил явную проверку `toHaveCount(1)`
для точного локатора кнопки. Это исключает выбор первой из нескольких одинаковых
кнопок и сохраняет проверку PUT и значения после перезагрузки.

Доказательства: целевой Playwright PASS; полный browser-набор PASS;
`npm run typecheck` PASS.

### 2026-08-12 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Кнопка сохранения настроек проверяется без `.first()` | `npm run test:browser` | PASS: 21 Playwright-сценарий, включая `edits pilot settings from the Settings screen` |
| Локатор однозначен перед нажатием | `web/e2e/control-plane.spec.ts`: `toHaveCount(1)` перед `.click()` | PASS: целевой E2E завершился успешно |
| Изменение не ломает соседнее поведение | `npm test` | PASS: 14 файлов, 158 тестов |
| Типы приложения корректны | `npx tsc -p tsconfig.app.json --noEmit` | PASS |

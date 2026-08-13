Implementation commit: ad763c7993aa2cdd52d18d96bd1d41078bccaab2 — E2E подтверждает единственность кнопки сохранения настроек

# CARD-0083 — Сохранение настроек без `.first()`

## HEAD

- Status: Implemented.
- Branch: `factory/2872a759-579-b8a15406-138`.
- Implementation commit: `ad763c7993aa2cdd52d18d96bd1d41078bccaab2` — E2E подтверждает единственность кнопки сохранения настроек.
- What changed: сценарий `/settings` находит кнопку строго внутри `.settings-page`, проверяет ровно один результат и нажимает его без `.first()`.
- Evidence: targeted Playwright PASS; полный Playwright PASS; `npm run typecheck` PASS.
- One next action: проверить поставку и влить её в `main`.

## LOG

### 2026-08-12 — Implement

После замечания Verify сценарий сохранения получил явную проверку `toHaveCount(1)`
для точного локатора кнопки. Это исключает выбор первой из нескольких одинаковых
кнопок и сохраняет проверку PUT и значения после перезагрузки.

Доказательства: целевой Playwright PASS; полный browser-набор PASS;
`npm run typecheck` PASS.

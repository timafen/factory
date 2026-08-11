# CARD-0073 — Визуальный аудит Плана, Уведомлений и русского интерфейса

## HEAD

- Status: Implement PASS — targeted browser checks зелёные.
- Branch: `factory/06aca8f6-f40-899f572b-747`.
Implementation commit: aad2e2236733c6faf9d7395a6bc86f59e78ccf17 — усилен locator кнопки сохранения Settings.
- What changed: Settings E2E scoped к `.settings-page`; кнопка выбирается exact role/name без `.first()`.
- Evidence: targeted Playwright visual audit, legacy migration and Settings — 3/3 passed; production не менялся.
- One next action: отправить ветку и подтвердить её через `git ls-remote`.

## LOG

### 2026-08-11 — Implement

После review исправлен ослабленный locator около `control-plane.spec.ts:1502`:
тест ограничен Settings-контейнером и использует `getByRole("button", { name: "Сохранить настройки", exact: true })`.
Убран `.first()`, поэтому дубликат кнопки или неверная область теперь ломают сценарий.
Targeted Playwright: `audits every Factory screen on desktop and phone`, legacy migration и Settings — 3 passed.

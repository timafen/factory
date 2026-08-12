# CARD-0073 — Визуальный аудит Плана, Уведомлений и русского интерфейса

## HEAD

- Status: Implement PASS — код поставлен, UI-проверки заблокированы повреждёнными npm-зависимостями.
- Branch: `factory/206f0982-6b7-71cc712c-e4f`.
Implementation commit: c01920f7dfd7a034f3e67ce4a0a7fbf77dfe4364 — проверка единственности кнопки сохранения Settings.
- What changed: Settings E2E scoped к `.settings-page`; кнопка выбирается exact role/name без `.first()`.
- Evidence: `just check` Go-часть PASS; целевой Playwright и UI-check не запустились: `playwright`/`eslint`/`tsc` отсутствуют в npm bin.
- One next action: повторить UI-проверки после исправления установки `web/node_modules`.

## LOG

### 2026-08-11 — Implement

После review исправлен ослабленный locator около `control-plane.spec.ts:1502`:
тест ограничен Settings-контейнером и использует `getByRole("button", { name: "Сохранить настройки", exact: true })`.
Убран `.first()`, поэтому дубликат кнопки или неверная область теперь ломают сценарий.
Targeted Playwright: `audits every Factory screen on desktop and phone`, legacy migration и Settings — 3 passed.

### 2026-08-12 — Implement

Перенесена только проверка текущей задачи на свежий `origin/main`: перед кликом
по кнопке «Сохранить настройки» E2E требует ровно один элемент в `.settings-page`.
Это делает случайный дубликат кнопки явной ошибкой проверки.

Доказательства: `just check` завершил Go vet, vulnerability scan, staticcheck и
`go test ./...`; UI-проверки заблокированы повреждённой npm-установкой (`tsc`,
`eslint` и Playwright CLI не находятся после `npm ci`).

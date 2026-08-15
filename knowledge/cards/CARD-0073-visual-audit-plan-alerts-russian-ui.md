# CARD-0073 — Визуальный аудит Плана, Уведомлений и русского интерфейса

## HEAD

- Status: Implement PASS — повторная проверка выполнена.
- Branch: `factory/28ac7d8f-a80-76906e4f-883`.
Implementation commit: 0579ce69eccea6d891668882d88689489e9909e4 — проверка единственности кнопки сохранения Settings.
- What changed: Settings E2E scoped к `.settings-page`; кнопка выбирается exact role/name без `.first()` и должна существовать в единственном числе.
- Evidence: `npm ci`, targeted Playwright Settings (1 passed) и `just check` PASS.
- One next action: передать в Verify.

## LOG

### 2026-08-15 — Specification

Спецификация визуального аудита перенесена на актуальную карточку CARD-0073.
Она определяет компактные реальные страницы Плана и Уведомлений, единый русский
словарь control plane, точечные responsive-исправления и browser-проверку
router-backed intake. Коллидирующая CARD-0174 не используется: этот номер
остаётся за самостоятельной работой о живой приёмке.

### 2026-08-11 — Implement

После review исправлен ослабленный locator около `control-plane.spec.ts:1502`:
тест ограничен Settings-контейнером и использует `getByRole("button", { name: "Сохранить настройки", exact: true })`.
Убран `.first()`, поэтому дубликат кнопки или неверная область теперь ломают сценарий.
Targeted Playwright: `audits every Factory screen on desktop and phone`, legacy migration и Settings — 3 passed.

### 2026-08-12 — Implement

После возврата задачи исправлена ссылка на фактический кодовый коммит реализации
`0579ce69eccea6d891668882d88689489e9909e4`; карточка перенесена на текущую ветку.
`npm ci` восстановил зависимости, targeted Playwright Settings: 1 passed.

Перенесена только проверка текущей задачи на свежий `origin/main`: перед кликом
по кнопке «Сохранить настройки» E2E требует ровно один элемент в `.settings-page`.
Это делает случайный дубликат кнопки явной ошибкой проверки.

Доказательства: `just check` завершил Go vet, vulnerability scan, staticcheck и
`go test ./...`; UI-проверки заблокированы повреждённой npm-установкой (`tsc`,
`eslint` и Playwright CLI не находятся после `npm ci`).

### 2026-08-12 — Implement

Зависимости интерфейса восстановлены воспроизводимо через `npm ci` из lock-файла
без изменения версий. Исправлен SHA реализации в HEAD: он указывает на существующий
кодовый коммит E2E, а не на ошибочно записанный идентификатор.

Доказательства: `npx tsc -p tsconfig.app.json --noEmit`, `npm run lint`, `npm test`
(158 passed), `npm run build`, E2E Settings и весь Playwright-набор (21 passed),
а также `just check` завершились PASS.

### 2026-08-12 — Implement

После обязательного rebase локальный кодовый дубликат был снят Git: идентичная
защита уже вошла в `main`. HEAD теперь ссылается на кодовый коммит-предок
`0579ce69eccea6d891668882d88689489e9909e4`, который меняет Settings E2E.

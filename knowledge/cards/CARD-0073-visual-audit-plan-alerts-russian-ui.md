# CARD-0073 — Визуальный аудит Плана, Уведомлений и русского интерфейса

## HEAD

- Status: Implement PASS — русский интерфейс и поставляемая сборка перенесены на свежий main.
- Branch: `factory/a834da11-81f-fc2043d9-131`.
Implementation commit: ede54d6e65fa00bf59f8b3d3482c4c0ef2062dd8 — русифицирован интерфейс управления и добавлены проверки.
- What changed: русские подписи, сообщения и форматы охватывают основные экраны; добавлены 21 браузерный сценарий и их fixture.
- Evidence: `npx tsc -p tsconfig.app.json --noEmit` завершилась без диагностик; `npm run build` сформировал и зафиксировал воспроизводимый `web/dist`.
- One next action: дождаться результата полного `npm run test:browser` и передать ветку.

## LOG

### 2026-08-11 — Implement

После review исправлен ослабленный locator около `control-plane.spec.ts:1502`:
тест ограничен Settings-контейнером и использует `getByRole("button", { name: "Сохранить настройки", exact: true })`.
Убран `.first()`, поэтому дубликат кнопки или неверная область теперь ломают сценарий.
Targeted Playwright: `audits every Factory screen on desktop and phone`, legacy migration и Settings — 3 passed.

### 2026-08-11 — Implement

Перенесены только файлы CARD-0073 на свежий `origin/main`, без истории старой ветки.
Явная проверка TypeScript прошла без диагностик; обновлён и закоммичен воспроизводимый `web/dist`.
Полный браузерный набор запущен после проверки совпадения generated assets.

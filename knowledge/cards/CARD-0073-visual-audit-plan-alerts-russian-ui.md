# CARD-0073 — Визуальный аудит Плана, Уведомлений и русского интерфейса

## HEAD

- Status: Implement PASS — review-блокеры устранены.
- Branch: `factory/383ce63b-579-070e13b1-6e9`.
Implementation commit: 1cddd85f3f92937685e1dee2e9b160c0908d8d9f — уведомления принимают только безопасные ссылки, а «Конвейер» полностью русифицирован.
- What changed: `javascript:` и чужие адреса не становятся ссылками; разрешены относительные маршруты и URL публичного Factory origin. Экран «Конвейер» и его браузерная проверка используют русский текст.
- Evidence: `python3 -m unittest pilot.test_pilot.PlanManualTaskTest` → 6 passed; `npm run test:browser -- --grep "audits every Factory screen on desktop and phone"` → целевой сценарий прошёл, bundle остался чистым.
- One next action: повторить Review.

## LOG

### 2026-08-12 — Implement

Устранён review-блокер с журналом уведомлений: ссылка проходит allowlist
относительных маршрутов и публичного Factory origin; негативный тест закрепляет
отклонение `javascript:`. Экран «Конвейер» и 21-экранный browser-аудит переведены
на русский. Целевые Python и browser-проверки прошли.

### 2026-08-11 — Implement

После review исправлен ослабленный locator около `control-plane.spec.ts:1502`:
тест ограничен Settings-контейнером и использует `getByRole("button", { name: "Сохранить настройки", exact: true })`.
Убран `.first()`, поэтому дубликат кнопки или неверная область теперь ломают сценарий.
Targeted Playwright: `audits every Factory screen on desktop and phone`, legacy migration и Settings — 3 passed.

### 2026-08-11 — Implement

Перенесены только файлы CARD-0073 на свежий `origin/main`, без истории старой ветки.
Явная проверка TypeScript прошла без диагностик; обновлён и закоммичен воспроизводимый `web/dist`.
Полный браузерный набор запущен после проверки совпадения generated assets.

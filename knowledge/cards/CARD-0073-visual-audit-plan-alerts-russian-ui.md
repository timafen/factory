# CARD-0073 — Визуальный аудит Плана, Уведомлений и русского интерфейса

## HEAD

- Status: Implement PASS — Review-блокер с языком документа устранён.
- Branch: `factory/36eea1d3-01e-ffd13838-85d`.
Implementation commit: 703bb6035fa5dd96395cdb28be12a1502498117c — русский интерфейс объявляет язык документа `ru` и проверяет это в browser-аудите.
- What changed: исходный HTML и поставляемый `web/dist/index.html` используют `lang="ru"`; аудит 21 экранов проверяет `document.documentElement.lang` в desktop и phone.
- Evidence: `npm run build` → прошла; `FACTORY_BROWSER_LAUNCHER=/tmp/factory-no-browser-launcher npx playwright test --grep "audits every Factory screen on desktop and phone"` → 1 passed (3.0m).
- One next action: повторить Review.

## LOG

### 2026-08-12 — Implement

Устранён блокер Review: русский интерфейс больше не объявлен английским
документом. `web/index.html` и воспроизводимый `web/dist` используют `lang="ru"`;
browser-аудит всех 21 экранов закрепляет проверку языка в desktop и phone.
Сборка прошла, а целевой Playwright-сценарий завершился успешно: 1 passed (3.0m).

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

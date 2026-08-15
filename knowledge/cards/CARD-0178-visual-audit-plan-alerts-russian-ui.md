Implementation commit: 44b9e6b3300ed2a2de8a7dca5555165b956a5d7d — компактный План, сгруппированные Уведомления и единый русский интерфейс

# CARD-0178 — Довести визуальный аудит до Плана, Уведомлений и единого языка

## HEAD

- Status: Implemented
- Branch: `factory/271a0ee6-6ea-25dc0272-b68`
- Implementation commit: `44b9e6b3300ed2a2de8a7dca5555165b956a5d7d`
- What changed: обоснование карточки Плана скрыто до запроса, а действия и служебные данные остаются на виду.
- What changed: Уведомления ограничены 30 свежими событиями, собраны по русским группам и раскрываются явно.
- What changed: основные экраны Factory переведены на русский и адаптированы для desktop и phone.
- Evidence: `python3 -m unittest pilot.test_pilot.PlanManualTaskTest` → 4 tests, OK.
- Evidence: `npm --prefix web test -- --run src/App.test.tsx src/Automations.test.ts` → 69 tests passed; второго файла в ветке нет, сценарии автоматизаций проверены в `App.test.tsx`.
- Evidence: `npx tsc -p tsconfig.app.json --noEmit`, lint и production build → passed; 1739 modules transformed.
- Evidence: Playwright `shows the real intake Plan and Alerts` → 1 passed; четыре снимка просмотрены вручную.
- Evidence: Playwright `audits every Factory screen on desktop and phone` → 1 passed.
- One next action: проверить `/intake/plan` на общем стенде после слияния ветки.

## LOG

### 2026-08-15 — Implement

Сделаны компактный План, сгруппированные Уведомления и русская терминология основных экранов. Реальные intake-обработчики проверены в Chromium на desktop и phone; общий визуальный аудит, компонентные и серверные тесты, типы, lint и production build прошли.

### 2026-08-15 — Implement

Реализация перенесена на итоговую ветку и перебазирована на свежий `main`. Повторный целевой прогон дал 69 успешных UI-тестов; типы проверены через `tsconfig.app.json`, lint, production build и 4 серверных теста Плана прошли. Запрошенный `src/Automations.test.ts` отсутствует в переданной истории, а сценарии автоматизаций остаются частью `App.test.tsx`.

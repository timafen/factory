Implementation commit: 60dc9f1d61135964a5112228949363271379f335 — компактный План, сгруппированные Уведомления и единый русский интерфейс

# CARD-0178 — Довести визуальный аудит до Плана, Уведомлений и единого языка

## HEAD

- Status: Implemented
- Branch: `factory/67f79a49-c0a-d2398fd0-8c0`
- Implementation commit: `60dc9f1d61135964a5112228949363271379f335`
- What changed: обоснование карточки Плана скрыто до запроса, а действия и служебные данные остаются на виду.
- What changed: Уведомления ограничены 30 свежими событиями, собраны по русским группам и раскрываются явно.
- What changed: основные экраны Factory переведены на русский и адаптированы для desktop и phone.
- Evidence: `python3 -m unittest pilot.test_pilot.PlanManualTaskTest` → 4 tests, OK.
- Evidence: `npm --prefix web test -- --run src/App.test.tsx src/Settings.test.tsx` → 78 tests passed.
- Evidence: typecheck, lint и production build → passed; 1739 modules transformed.
- Evidence: Playwright `shows the real intake Plan and Alerts` → 1 passed.
- Evidence: Playwright `audits every Factory screen on desktop and phone` → 1 passed.
- One next action: проверить `/intake/plan` на общем стенде после слияния ветки.

## LOG

### 2026-08-15 — Implement

Сделаны компактный План, сгруппированные Уведомления и русская терминология основных экранов. Реальные intake-обработчики проверены в Chromium на desktop и phone; общий визуальный аудит, компонентные и серверные тесты, типы, lint и production build прошли.

### 2026-08-15 — Implement

После переноса на свежий `origin/main` обновлена ссылка на фактический коммит реализации. Повторно прошли целевые серверные и UI-тесты, typecheck, lint, production build и обе browser-проверки: реальный intake План/Уведомления и аудит всех экранов desktop/phone.

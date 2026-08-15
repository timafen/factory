Implementation commit: 839b421fa40099a711f9b8a089d4539e054fe044 — русский язык постановки и просмотра задач, конвейера и статусов автоматизаций

# CARD-0178 — Довести визуальный аудит до Плана, Уведомлений и единого языка

## HEAD

- Status: Implemented
- Branch: `factory/ad25d359-9c8-61c8396c-b18`
- Implementation commit: `839b421fa40099a711f9b8a089d4539e054fe044`
- What changed: обоснование карточки Плана скрыто до запроса, а действия и служебные данные остаются на виду.
- What changed: Уведомления ограничены 30 свежими событиями, собраны по русским группам и раскрываются явно.
- What changed: постановка, просмотр задач и Конвейер переведены на русский; проверки закрепляют русские подписи.
- What changed: статусы автоматизаций берутся по стабильному коду, а неизвестный текст сервера заменяется безопасным русским сообщением.
- Evidence: `python3 -m unittest pilot.test_pilot.PlanManualTaskTest` → 4 tests, OK.
- Evidence: `npm --prefix web test -- --run src/App.test.tsx src/Settings.test.tsx` → 78 tests passed.
- Evidence: `npx --prefix web tsc -p web/tsconfig.app.json --noEmit` → passed.
- Evidence: `npm --prefix web run build` → passed; 1739 modules transformed.
- Evidence: Playwright `shows the real intake Plan and Alerts` → 1 passed; четыре снимка просмотрены вручную.
- Evidence: Playwright `audits every Factory screen on desktop and phone` → 1 passed.
- One next action: проверить экран «Работы» на общем стенде после слияния ветки.

## LOG

### 2026-08-15 — Implement

Сделаны компактный План, сгруппированные Уведомления и русская терминология основных экранов. Реальные intake-обработчики проверены в Chromium на desktop и phone; общий визуальный аудит, компонентные и серверные тесты, типы, lint и production build прошли.

### 2026-08-15 — Implement

Постановка и просмотр задач, а также Конвейер переведены на русский. Сообщения автоматизаций локализуются по стабильным кодам, а неизвестные серверные диагностики заменяются безопасным русским текстом; TypeScript и production build прошли.

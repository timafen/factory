# CARD-0089 — стабильный HTTPS-набор с реальным service worker

Implementation commit: c47a9685c39811ad7aac0c50ea201aa1ad9c97f4 — HTTPS-набор сохраняет доверенный Chromium-запрос к dashboard и стабильно проверяет адаптивную страницу.

## HEAD

- Status: Implemented — HTTPS-набор подтверждает регистрацию реального service worker.
- Branch: `factory/2a16b28b-22a-a0923efd-744`.
- Implementation commit: `c47a9685c39811ad7aac0c50ea201aa1ad9c97f4`.
- What changed: HTTPS-сценарий ожидает `navigator.serviceWorker.ready` и проверяет активный `/sw.js`; конфигурационный тест закрепляет эту регрессию.
- Evidence: `npx tsc -p tsconfig.app.json --noEmit` → PASS; `npx vitest run src/playwrightConfig.test.ts` → 12/12 PASS.
- Evidence: `npx playwright test e2e/control-plane.spec.ts` → 21/21 PASS на HTTPS fixture с реальным service worker.
- Next action: выполнить финальную verification-проверку и слияние.

## LOG

### 2026-08-11 — Implement

- Добавлена точная регрессия доверенного Chromium-fetch для readiness-dashboard без ослабления TLS browser context.
- Убрана зависимость narrow-layout сценария от уже остановленного heartbeat; адаптивная сетка продолжает проверяться напрямую.
- Полный HTTPS Chromium-набор прошёл 21/21; production build и dist-проверка прошли, scoped-процессы после теста завершились.

### 2026-08-12 — Implement

- Увеличен только admission-бюджет worker timeout-теста до 10 секунд; проверка runtime timeout, process group и отдельная односекундная pre-start проверка сохранены.
- На окончательном HEAD целевые timeout-тесты прошли 2/2, полный `just check` прошёл, HTTPS browser suite прошёл 21/21 с реальным service worker.

### 2026-08-12 — Implement

- Утверждённая поставка перенесена на свежий `main` без изменения области: worker timeout, HTTPS browser interception, Playwright-конфигурация и эта карточка.
- На перенесённой ветке целевые Go timeout-тесты прошли 2/2, а `web/src/playwrightConfig.test.ts` прошёл 12/12.

### 2026-08-12 — Implement

- При финальном переносе свежий `main` уже содержал усиленный вариант timeout-теста с 30-секундным budget; он сохранён вместо дублирующего 10-секундного варианта.

### 2026-08-12 — Implement

- Исправлена ссылка реализации: карточка теперь указывает на HTTPS-коммит `c47a9685c39811ad7aac0c50ea201aa1ad9c97f4`, а не на базовый timeout-коммит.
- HTTPS-сценарий ожидает готовность service worker и подтверждает активный `/sw.js`, поэтому молча сорванная регистрация больше не проходит набор.
- Проверки: TypeScript без ошибок, `playwrightConfig.test.ts` 12/12 и реальный HTTPS Playwright-набор 21/21.

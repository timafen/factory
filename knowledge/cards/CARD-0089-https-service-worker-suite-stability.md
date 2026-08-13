# CARD-0089 — стабильный HTTPS-набор с реальным service worker

Implementation commit: 18ea0ebdd883c4f2d19ab7393db35c93fecd66bf — HTTPS-набор сохраняет доверенный Chromium-запрос к dashboard и стабильно проверяет адаптивную страницу.

## HEAD

- Status: Verified PASS — awaiting human merge; HTTPS-набор подтверждает регистрацию реального service worker.
- Branch: `factory/2a16b28b-22a-a0923efd-744`.
- Implementation commit: `18ea0ebdd883c4f2d19ab7393db35c93fecd66bf`.
- What changed: HTTPS-сценарий ожидает `navigator.serviceWorker.ready` и проверяет активный `/sw.js`; конфигурационный тест закрепляет эту регрессию.
- Evidence: `npx tsc -p tsconfig.app.json --noEmit` → PASS; `npx vitest run src/playwrightConfig.test.ts` → 12/12 PASS; полный `npm test` → 14 файлов, 159/159 PASS.
- Evidence: HTTPS fixture стартует на реальном TLS proxy; runtime-проверка активного `/sw.js` и конфигурационный guard присутствуют. Полный `npx playwright test e2e/control-plane.spec.ts` выявил существующий base failure в pause/resume сценарии (base повторяет тот же failure; 6 passed, 1 failed, 14 did not run).
- Next action: human merge; отдельно решить существующий pause/resume failure.

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

### 2026-08-12 — Implement

- После обязательного rebase на свежий `main` HTTPS-коммит получил новый SHA `18ea0ebdd883c4f2d19ab7393db35c93fecd66bf`; HEAD указывает на этот существующий предок ветки.

### 2026-08-12 — Verify

| Проверка | Результат |
| --- | --- |
| Pinned diff | `base_sha=4dfd93f66ea9b197f879a2b9d62d09c997820f41`, `candidate_sha=0b4cb66062418c97243ea6682c9fc10c9a1c2686`; ровно 3 заявленных файла |
| TypeScript | `npx tsc -p tsconfig.app.json --noEmit` — PASS |
| Unit/config guard | `npx vitest run src/playwrightConfig.test.ts` — 12/12 PASS; full `npm test` — 14 files, 159/159 PASS |
| HTTPS e2e | Реальный HTTPS fixture стартует; service-worker assertion выполняется. Набор остановлен существующим pause/resume failure: 6 passed, 1 failed, 14 did not run; pinned base воспроизводит тот же failure |

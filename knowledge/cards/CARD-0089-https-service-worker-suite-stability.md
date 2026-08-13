# CARD-0089 — стабильный HTTPS-набор с реальным service worker

Implementation commit: 9bb77821f62f644c75b7b8c602b83949137343ea — worker timeout-тест получает запас на подготовку worktree и стабильно проверяет остановку process group.

## HEAD

- Status: Implemented — утверждённая HTTPS-поставка перенесена на свежий `main`.
- Branch: `factory/5be5c3c1-15d-5d14551f-d3c`.
- Implementation commit: `9bb77821f62f644c75b7b8c602b83949137343ea`.
- What changed: `TestTimeoutStopsIgnoringProcessGroup` получает 10 секунд на admission и проверяет реальный runtime timeout; односекундная граница подготовки остаётся в отдельном `TestTimeoutIncludesWorktreePreparation`.
- Evidence: целевые Go timeout-тесты → 2/2 PASS; UI-конфигурация Playwright → 12/12 PASS после переноса.
- Evidence: утверждённая исходная поставка → HTTPS browser suite 21/21 PASS с реальным service worker.
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

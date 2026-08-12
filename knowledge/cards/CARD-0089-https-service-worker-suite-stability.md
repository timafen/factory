# CARD-0089 — стабильный HTTPS-набор с реальным service worker

Implementation commit: 78cf262f967a92adf0bbb1ac0d2a9efa9b0f6055 — worker timeout-тест получает запас на подготовку worktree и стабильно проверяет остановку process group.

## HEAD

- Status: Verified PASS — полный HTTPS browser suite и полный check прошли.
- Branch: `factory/29d8fbbb-45a-61b50a9f-f39`.
- Implementation commit: `78cf262f967a92adf0bbb1ac0d2a9efa9b0f6055`.
- What changed: `TestTimeoutStopsIgnoringProcessGroup` получает 10 секунд на admission и проверяет реальный runtime timeout; односекундная граница подготовки остаётся в отдельном `TestTimeoutIncludesWorktreePreparation`.
- Evidence: целевые timeout-тесты → 2/2 PASS на окончательном HEAD.
- Evidence: `just check` → PASS: Go, vuln/staticcheck, UI 158 тестов, build/tooling/launcher.
- Evidence: `FACTORY_BROWSER_LAUNCHER=/missing just test-browser` → 21/21 PASS за 4,7 минуты, включая HTTPS resume/Origin, scoped SPKI и реальный service worker.
- Next action: слить ветку после подтверждённого push.

## LOG

### 2026-08-11 — Implement

- Добавлена точная регрессия доверенного Chromium-fetch для readiness-dashboard без ослабления TLS browser context.
- Убрана зависимость narrow-layout сценария от уже остановленного heartbeat; адаптивная сетка продолжает проверяться напрямую.
- Полный HTTPS Chromium-набор прошёл 21/21; production build и dist-проверка прошли, scoped-процессы после теста завершились.

### 2026-08-12 — Implement

- Увеличен только admission-бюджет worker timeout-теста до 10 секунд; проверка runtime timeout, process group и отдельная односекундная pre-start проверка сохранены.
- На окончательном HEAD целевые timeout-тесты прошли 2/2, полный `just check` прошёл, HTTPS browser suite прошёл 21/21 с реальным service worker.

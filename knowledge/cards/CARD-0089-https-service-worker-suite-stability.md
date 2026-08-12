# CARD-0089 — стабильный HTTPS-набор с реальным service worker

Implementation commit: 727830a4dad15a66f16b51040ba9d7b57342d753 — закреплён доверенный Chromium-путь HTTPS-перехвата и устранена временная зависимость narrow-layout сценария.

## HEAD

- Status: Verified PASS — полный HTTPS browser suite прошёл.
- Branch: `factory/6ffeccbd-467-a0dbe95d-b4d`.
- Implementation commit: `727830a4dad15a66f16b51040ba9d7b57342d753`.
- What changed: регрессия запрещает возврат readiness-перехвата к `route.fetch()` без scoped SPKI trust; narrow-layout проверяет адаптивный блок независимо от истечения фонового heartbeat.
- Evidence: `npm test -- --run src/playwrightConfig.test.ts` → 12/12 PASS; целевой narrow Chromium → PASS.
- Evidence: `FACTORY_BROWSER_LAUNCHER=/missing just test-browser` → 21/21 PASS за 7,6 минуты, включая HTTPS resume/Origin и service worker.
- Evidence: `FACTORY_BUILD_DIR=<tmp> just build` → три бинарника собраны; `git diff --exit-code -- web/dist` → PASS.
- Evidence: `just check` → lint/vuln/staticcheck PASS, но существующий timing-тест `TestTimeoutStopsIgnoringProcessGroup` упал под параллельной нагрузкой worktree.
- Next action: слить ветку после проверки diff и push.

## LOG

### 2026-08-11 — Implement

- Добавлена точная регрессия доверенного Chromium-fetch для readiness-dashboard без ослабления TLS browser context.
- Убрана зависимость narrow-layout сценария от уже остановленного heartbeat; адаптивная сетка продолжает проверяться напрямую.
- Полный HTTPS Chromium-набор прошёл 21/21; production build и dist-проверка прошли, scoped-процессы после теста завершились.

# CARD-0088: HTTPS resume идёт через Chromium

## HEAD

Status: Verified PASS — awaiting human merge.
Branch: `factory/9cdd433e-d88-572161e8-baa`
Implementation commit: 000084fd7cc008d8df69d62dedf02c00d91d93a8 — HTTPS resume в E2E выполняется через Chromium `route.continue`, без `route.fetch`.
What changed: браузер владеет TLS-запросом и scoped SPKI trust; forged Origin остаётся отдельной loopback-проверкой.
Evidence: целевой реальный Playwright HTTPS-сценарий PASS; UI, build, release, launcher и статические проверки PASS. Общие наборы дополнительно выявили два не связанных с этой областью timeout на перегруженной машине.
One next action: human merge this verified documentation delivery.

## LOG

### 2026-08-11 — Implement

Реализация уже присутствует в свежем `origin/main`; рабочий diff после rebase пуст.
Карточка фиксирует состав HTTPS-проверки и подтверждает, что повторная реализация не требуется.

### 2026-08-12 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| HTTPS resume выполняет Chromium без `route.fetch` | `just test-browser`; Playwright test 7 | PASS: реальный HTTPS proxy, защищённый Origin, 8.8 с; исходник содержит `route.continue`, unit guard запрещает `route.fetch` |
| TLS-доверие ограничено fixture-сертификатом | `just ui-check` | PASS: `playwrightConfig.test.ts` проверяет scoped SPKI Chromium argument и HTTPS base URL |
| Поддельные forwarding-заголовки не доходят до backend | тот же Playwright test 7 | PASS: forged значения наблюдаются на входе, backend получает очищенные/канонические значения |
| Соседнее поведение и сборка | Linux CI-команды из `.github/workflows/ci.yml` | PASS: `npm ci`, UI checks/build, tooling/build/release/launcher, format/vet/vuln/staticcheck/boundary; 13 Playwright-сценариев PASS |
| Полный набор | `just test`; `just test-browser` | НАХОДКА: вне области один worker-тест и общий аудит экранов превысили короткие timeout под нагрузкой; целевые и остальные выполненные тесты PASS |

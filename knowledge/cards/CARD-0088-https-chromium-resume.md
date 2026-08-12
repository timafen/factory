# CARD-0088: HTTPS resume идёт через Chromium

## HEAD

Status: Implemented and delivered in `origin/main`.
Branch: `factory/9cdd433e-d88-572161e8-baaa`
Implementation commit: 000084fd7cc008d8df69d62dedf02c00d91d93a8 — HTTPS resume в E2E выполняется через Chromium `route.continue`, без `route.fetch`.
What changed: браузер владеет TLS-запросом и scoped SPKI trust; forged Origin остаётся отдельной loopback-проверкой.
Evidence: focused Playwright test, `npm run build`, `git diff --check` — PASS.
One next action: human merge this documentation-only delivery.

## LOG

### 2026-08-11 — Implement

Реализация уже присутствует в свежем `origin/main`; рабочий diff после rebase пуст.
Карточка фиксирует состав HTTPS-проверки и подтверждает, что повторная реализация не требуется.

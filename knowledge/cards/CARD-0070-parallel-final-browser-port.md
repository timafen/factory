Implementation commit: 4577b5770bfef904d31d85630c6a88af4e720108 — параллельные браузерные проверки выбирают разные согласованные loopback-порты.

# CARD-0070 — Параллельные финальные браузерные проверки

## HEAD

- Status: Implemented and tested — awaiting Verify.
- Branch: `factory/d1e33ea5-cbc-8286b56e-ede`.
- Implementation commit: `4577b5770bfef904d31d85630c6a88af4e720108`.
- What changed: Playwright выбирает свободный порт, закрепляет его для повторной
  загрузки config и передаёт серверу; worker, legacy poller, health-check,
  browser и прямые E2E API-клиенты используют один адрес.
- Evidence: целевой Vitest — 10 passed; typecheck и lint — PASS; два одновременных
  `npm run test:browser` слушали `127.0.0.1:46129` и `127.0.0.1:44143`, оба —
  20 passed с exit 0, без bind/EADDRINUSE.
- Open risk: выбор свободного порта сохраняет малое TOCTOU-окно; системный
  browser-sandbox в текущем контейнере блокируется `no_new_privileges`, поэтому
  параллельное доказательство выполнено через штатный launcher override.
- One next action: на стадии Verify один раз выполнить полный набор проекта.

## LOG

### 2026-08-11 — Implement

Убран общий порт `17437`: автоматически выделенный порт согласован между всеми
частями browser fixture и может быть явно задан через `FACTORY_E2E_PORT`.
Целевой тест подтвердил валидные, невалидные и независимые порты. Два полных
браузерных прогона в отдельных временных клонах одновременно прошли по 20 тестов;
логи сохранены в `/tmp/factory-browser-parallel-verified-{1,2}.log`.

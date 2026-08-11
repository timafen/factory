Implementation commit: 4577b5770bfef904d31d85630c6a88af4e720108 — параллельные браузерные проверки выбирают разные согласованные loopback-порты.

# CARD-0071 — Параллельные финальные браузерные проверки

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/d1e33ea5-cbc-8286b56e-ede`.
- Implementation commit: `4577b5770bfef904d31d85630c6a88af4e720108`.
- What changed: Playwright выбирает свободный порт, закрепляет его для повторной
  загрузки config и передаёт серверу; worker, legacy poller, health-check,
  browser и прямые E2E API-клиенты используют один адрес.
- Evidence: чистый `npm ci`; `go test ./...`, typecheck, lint и Vitest (154)
  прошли. Два одновременных Playwright-прогона в изолированных клонах слушали
  `127.0.0.1:46841` и `127.0.0.1:35547`; каждый завершился `20 passed` без
  bind/EADDRINUSE.
- Open risk: выбор свободного порта сохраняет малое TOCTOU-окно между проверкой
  и bind; штатная retry-логика сервера не добавлялась.
- One next action: человек выполняет merge delivery-ветки.

## LOG

### 2026-08-11 — Implement

Убран общий порт `17437`: автоматически выделенный порт согласован между всеми
частями browser fixture и может быть явно задан через `FACTORY_E2E_PORT`.
Целевой тест подтвердил валидные, невалидные и независимые порты. Два полных
браузерных прогона в отдельных временных клонах одновременно прошли по 20 тестов;
логи сохранены в `/tmp/factory-browser-parallel-verified-{1,2}.log`.

### 2026-08-11 — Verify

| Проверка | Команда/наблюдение | Результат |
| --- | --- | --- |
| Полный Go-набор | `go test ./...` | PASS |
| UI-набор после чистой установки | `npm ci`; `npm run typecheck`; `npm run lint`; `npm test` | PASS; 14 файлов, 154 теста |
| Сборка и чистота generated output | `npm run build`; `git diff --exit-code -- dist` | PASS |
| Параллельные browser suite | два `npx playwright test` в изолированных клонах | PASS; по 20 тестов за 3.8m |
| Разделение портов | процессы `factory-server -listen` во время параллельного запуска | `127.0.0.1:46841` и `127.0.0.1:35547`; `EADDRINUSE` отсутствует |

Рабочее дерево и `dist` проверены чистыми; `git diff --check` не сообщил ошибок.

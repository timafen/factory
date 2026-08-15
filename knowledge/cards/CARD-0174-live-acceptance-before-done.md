# CARD-0174 — Завершение только после живой приёмки

Implementation commit: df6aceb59d0f990e1fd7316bfac99e3047c905f2 — broker публикует single-flight живую приёмку без ожидания checker, а завершённый выпуск получает finished_at после PASS.

## HEAD

- Status: Blocked — worker не может штатно вызвать `sudo` для перезапуска broker.
- Branch: `factory/0f12da99-439-72bd6b1b-800`.
- Implementation commit: `df6aceb59d0f990e1fd7316bfac99e3047c905f2`.
- What changed: POST живой приёмки durable сохраняет `running`, запускает
  checker в фоне и сразу открывает single-flight наблюдение; terminal результат
  публикуется только после записи. Успешный тестовый выпуск моделирует PASS
  приёмки и проверяет `finished_at` в dashboard-проекции.
- Evidence: `GOCACHE=/tmp/... go test ./internal/releasebroker` → PASS;
  разрешённый `sudo -n systemctl restart factory-release-broker.service` → не
  запущен из-за `no_new_privileges`.
- Next action: повторить перезапуск, выпуск и живую приёмку из privileged worker.

## LOG

### 2026-08-15 — Release retry blocked

Владелец разрешил штатный перезапуск broker, но текущий Factory worker не может
вызвать `sudo`: включён `no_new_privileges`, а `/etc/sudo.conf` имеет неверного
владельца. Поэтому `fx factory release` не запускался, production не менялся и
автоматический откат не требовался; непривилегированная диагностика не видит
unit и journal хоста. До блокировки подтверждены прежние полный набор checks.

### 2026-08-15 — Release blocked

Проверенный результат интегрирован в `main`, но штатный `fx factory release`
безопасно остановился до первой мутации: `factory-release-broker.service`
использует deleted-inode. Production продолжает работать на прежней версии;
живая приёмка не запускалась. Владельцу отправлено срочное уведомление в ntfy.

### 2026-08-15 — Implement

Исправлены блокеры Verify: HTTP POST больше не ждёт живой checker, поэтому
повторный запрос немедленно наблюдает единственный durable `running`; после
PASS результат появляется через GET. Dashboard-регрессия теперь проходит весь
release → acceptance PASS переход и подтверждает `finished_at`. Полные gates
`just build`, `just format-check`, `just vet`, `just boundary`, `just test` и
`npx tsc -p tsconfig.app.json --noEmit` — PASS.

### 2026-08-15 — Implement

Устранены блокеры Review: unconfigured broker больше не может завершить живую
приёмку PASS, а параллельный POST видит durable `running` и не запускает checker
повторно. После рестарта незавершённый checker fail-closed. Регрессии доказывают
immutable identity, единственный запуск, restart recovery и read-only fixture:
`go test ./internal/releasebroker`, `bash ops/test-factory-live-acceptance.sh`,
`bash ops/test-install-project-release-broker.sh` — PASS.

### 2026-08-15 — Implement

Реализована отдельная post-release acceptance boundary: release сам по себе не
публикует Done. Broker сохраняет immutable результат fixed executable, а Pilot
создаёт receipt/outbox/final success только после PASS; FAIL записывает
`live-failed` и дедуплицированно возвращает waits в Implement + Test. Проверены
`go test ./internal/releasebroker` и `bash ops/test-install-project-release-broker.sh`.

### 2026-08-15 — Specification

Фактический `pilot/pilot.py` завершает generation непосредственно по broker
`succeeded`. Определена отдельная durable фаза `released`, acceptance operation
с тем же immutable generation ID, идемпотентные PASS/FAIL side effects и
fail-closed recovery. PASS единственный создаёт receipt, final success и Done;
FAIL сохраняет безопасную причину и возвращает работу в `Implement + Test`.

Production fixture выбран read-only: встроенный offline-retained snapshot и
живой workers snapshot проходят один parser. Проверка не вызывает janitor,
mutating API, systemd или worktree cleanup, но сохранённая живая запись
обязательно приводит к FAIL.

## Связи

- CARD-0084 — базовая durable машина слияния и выпуска.
- CARD-0048 — точечное подтверждение очистки offline retained-worktree.
- CARD-0092 — durable terminal status release broker.

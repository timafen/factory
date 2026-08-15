# CARD-0174 — Завершение только после живой приёмки

Implementation commit: e0b5f52b40a03e2c6f48d7250694f73d40574372 — broker fail-closed выполняет живую приёмку ровно один раз и сохраняет безопасный результат после рестарта.

## HEAD

- Status: Implemented — ожидает Verify.
- Branch: `factory/de5afa43-4c3-962238f3-84d`.
- Implementation commit: `e0b5f52b40a03e2c6f48d7250694f73d40574372`.
- What changed: отсутствие fixed checker записывает FAIL, не PASS; повторный
  POST при running не создаёт второй процесс; restart переводит uncertain
  checker в durable FAIL. Добавлены регрессии broker и read-only fixture.
- Evidence: `just check` → PASS; `go test ./internal/releasebroker` → PASS; acceptance and installer shell tests → PASS.
- Next action: выполнить полный набор проверок на свежем `main` перед Verify.

## LOG

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

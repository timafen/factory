# CARD-0174 — Завершение только после живой приёмки

Implementation commit: e0123dc69dc130b93e15da0ddce7c2a0a1efc691 — Pilot ждёт живую приёмку после выпуска, а broker сохраняет результат fixed read-only checker.

## HEAD

- Status: Implemented — ожидает Verify.
- Branch: `factory/3cc81421-187-9a740feb-827`.
- Implementation commit: `e0123dc69dc130b93e15da0ddce7c2a0a1efc691`.
- What changed: broker success становится durable `released`; PASS единственный
  завершает waits. Fixed checker читает health/current release/workers и FAIL
  возвращает Verify в `Implement + Test` без успешных артефактов.
- Evidence: `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` → PASS; `go test ./internal/releasebroker` → PASS; installer shell test → PASS.
- Next action: на Verify добавить/запустить полный набор регрессий Pilot и живого checker.

## LOG

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

# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Verified PASS — ожидает слияния человеком.
- Branch: `factory/e9c8b551-321-462fb670-02d`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 0efd98429300891a8918e207ace684b7d955e8b4 — временная недоступность broker не создаёт новый физический выпуск, а terminal checkpoint удерживает active до durable записи.
- What changed: Pilot сохраняет `launching`/`running` при неответившем GET и повторяет проверку прежнего operation id.
- What changed: Broker освобождает `active` только после успешного сохранения terminal status; регрессии покрывают оба отказа.
- Evidence: `go test -count=1 ./internal/releasebroker` → OK (9); `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` → OK (11); `just build` → OK; `just check` → OK; `git diff --check` → passed.
- Next action: Человеку проверить и принять изменения в ветке.

## LOG

### 2026-08-11 — Specification

Specification accepted a durable V2 generation model: release completion is
authoritative only after broker acceptance, while old delivery state is audit-only.

### 2026-08-11 — Implement

Implemented the V2 generation lifecycle, durable broker operations and the
generation-aware Factory release driver. Pilot completion waits for accepted
release status and records receipts/outbox by immutable delivery id.

### 2026-08-11 — Implement

Review fixes make the Pilot Unix-socket POST match the broker API, preserve
journal/wait/outbox recovery boundaries, and allow only `rc=8` operations to
re-enter the executor. State-file restarts, real Unix-socket protocol coverage,
physical executor counts and full Python/broker/shell checks provide evidence.

### 2026-08-11 — Implement

Correction replaces the hand-written Python socket with the built Go broker,
its real Unix API, and a fixed FX executor fixture. Restart boundaries now
drive recovery to completion with explicit merge/POST/physical/owner counts;
the lock retry joins a second merge to the same N and succeeds once.

### 2026-08-11 — Implement

Third strict-review correction keeps adapter and derived target immutable after
`rc=8`, while allowing only the same delivery id to retry with a new commit SHA.
The process fixture now exits a real Pilot after every durable delivery boundary,
recovers against the built Unix broker and physical FX, and proves failed terminals
cannot create receipts, finalization, or owner completion.

### 2026-08-11 — Implement

Terminal and restart-recovery states are now published only after the matching
operation record is persisted. A real filesystem write failure followed by a
fresh broker and Pilot process proves one physical delivery, durable fail-closed
recovery, and no receipt, outbox, finalization or owner completion.

### 2026-08-11 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Terminal recovery | `go test -count=1 ./internal/releasebroker` | 9 OK; отказ записи не публикует terminal, fresh restart даёт `failed`, executor остаётся один. |
| Fail-closed готовность | `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` | 10 OK; процессный restart не создаёт receipt, outbox, `mark_final(true)` или owner done. |
| Соседние recovery/lock/outbox сценарии | тот же Pilot class | OK: crash boundaries, lock join, N+1, immutable journals и legacy audit-only. |
| Сборка и чистота | `FACTORY_DATA_HOME=$(mktemp -d ...) just build`; `git diff --check` | Собраны три бинаря; whitespace ошибок нет. |
| Полный регресс | `just check`; отдельно `go test -timeout 25s -count=1 ./internal/controlplane` | Не завершён: независимый control-plane timeout на SQLite migration (`TestHTTPEfficiencyReturnsBothFixedComparablePeriods`); файлы control-plane не менялись. |

### 2026-08-11 — Implement

Временный отказ GET статуса больше не превращает `launching`/`running` в
`failed`: Pilot сохраняет поколение и повторяет проверку его immutable id.
Broker удерживает `active`, пока terminal status не сохранён надёжно; целевые
Go и Pilot регрессии, сборка и полный `just check` прошли успешно.

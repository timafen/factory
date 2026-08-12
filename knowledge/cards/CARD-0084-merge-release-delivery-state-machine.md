# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Verified PASS — ожидает human merge.
- Branch: `factory/9a5f1881-8de-c3901c14-426`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 00692b43dcbfc11524d0a866b8bde42a96d50542 — финальный `succeeded` драйвера проверяется явно.
- What changed: Отказ atomic write после физического выпуска возвращает ошибку, не публикуя durable `succeeded`.
- What changed: Fresh broker/Pilot restart сохраняет failed outcome, один executor и отсутствие receipt, outbox, `mark_final` и owner done.
- Evidence: 5 целевых Go-проверок и 10 процессных Python-проверок проходят; полный Go-набор упирается в старый timeout `internal/worker`, который не входит в поставку.
- Next action: Выполнить human merge после учёта независимого timeout `internal/worker`.

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

### 2026-08-11 — Implement

The release driver now checks its authoritative final `succeeded` write and
returns a non-success result when that atomic rename fails after physical
delivery. A real shell fault plus fresh broker and Pilot processes prove one
executor, durable failure and no receipt, outbox, finalization or owner completion.

### 2026-08-12 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Ошибка финальной записи не становится успехом | `go test -count=1 -v ./internal/releasebroker -run '^(TestBrokerDoesNotPublishTerminalSuccessWhenPersistFails|TestTerminalWriteFailureNeverPublishesSuccessOrRepeatsExecutorAfterRestart)$'` | OK: API и файл остаются `running`; после restart — `failed`, физический executor вызван один раз. |
| Pilot не завершает выпуск без durable terminal | `python3 -m unittest -v pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` | 10 OK: реальный Unix broker, restart, receipts/outbox/finalization и owner completion проверены процессно. |
| Смежные сценарии | Те же Go/Python проверки | OK: lock retry допускает только тот же adapter/target, immutable identity и crash recovery сохранены. |
| Полный Go-регресс | `go test -count=1 -timeout 5m ./...` | `internal/worker` timeout через 300.237s в `repository_coordination_test`; пакет не менялся этой поставкой. |

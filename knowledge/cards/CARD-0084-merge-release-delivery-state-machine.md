# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/bc99756f-1a9-d090f4e4-78d`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 3085c03f25cfa2184abff882f93185ffd46e86d3 — реальный Unix broker подтверждает восстановление одного выпуска.
- What changed: Pilot-тест собирает и запускает Go broker на Unix-сокете, проходит API и один физический FX executor.
- What changed: Все restart boundaries считают merge/POST/physical/owner done; `rc=8` retry завершает тот же N без N+1.
- Evidence: `just check` → OK; real Unix broker recovery tests → OK (3); broker Go tests and release/install shell fixtures → OK.
- Next action: Human merge the verified delivery recovery change.

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

### 2026-08-12 — Verify

| Acceptance criterion | Command/check | Observed result |
| --- | --- | --- |
| Durable V2, recovery and one physical delivery | `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests.test_state_file_restart_boundaries_keep_one_delivery_identity` | OK: every restart boundary keeps one delivery identity, one POST, one physical execution and one owner completion. |
| Lock joins N; later work becomes N+1 | `...test_locked_join_uses_latest_snapshot_and_one_physical_retry` | OK: two waits join N, retry succeeds once physically, no extra generation. |
| Real broker API and fixed executor | `...test_pilot_uses_real_unix_broker_routes` | OK: test builds the Go broker, uses its Unix socket and executes the FX fixture once. |
| Broker durability and release driver | `go test ./internal/releasebroker -count=1`; `bash ops/test-fx-factory-release.sh`; `bash ops/test-install-project-release-broker.sh` | All passed. |
| Full project regression suite | `just check` | Passed from a clean worktree. |
| Scope isolation | pinned `fc3af293e5e2b2c3802ad9b1d376f7796aa3b067...ed4520b9afaee36ea85f24e86b0faee344d34391` comparison | No UI, migrations or control-plane files changed. |

Live staging bootstrap was attempted only as permitted, but non-interactive
sudo is unavailable on this worker; the real Unix-broker fixture above remains
the executable proof of broker recovery.

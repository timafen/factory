# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Implemented — доказательство перезапуска усилено после строгого review.
- Branch: `factory/e783f445-945-25356772-a70`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 0c3997247d848a6df447b705f92600f09f4d9f60 — реальный broker и отдельные Pilot-процессы доказывают recovery выпуска.
- What changed: Каждая crash boundary запускается через отдельный persisted Pilot process и восстанавливается свежим process против собранного Go broker.
- What changed: Broker сохраняет счётчик POST; lock retry сохраняет N, принимает SHA второго merge до первого принятого выпуска и достраивает completed receipts после restart.
- Evidence: `python3 -m unittest pilot.test_pilot` → OK; `go test ./internal/releasebroker` → OK; обе shell fixture → OK; `just check` → passed.
- Next action: Review проверить process-level crash evidence CARD-0084.

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

Strict review correction replaces the in-memory phase fixture with independent
Pilot interpreter invocations over one persisted state/journal and the built
Unix broker. The broker durably records every POST; a locked N accepts the
second merge snapshot before its single successful physical installation, and
recovery from durable `completed` writes its missing receipts/outbox exactly once.

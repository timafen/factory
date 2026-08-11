# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Implemented — исправления третьего строгого review готовы к повторной проверке.
- Branch: `factory/4b80f667-aa4-f342742f-30a`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 380e77b1223a16a6608134e3d002f0d9629988ad — retry после `rc=8` сохраняет неизменный adapter/target и реальные crash boundaries.
- What changed: Broker принимает новый SHA того же delivery id только при том же adapter/target; rollback и чужой target атомарно отклоняются.
- What changed: Реальный FX PID и terminal phase сохраняются до recovery; отдельные Pilot-процессы проверяют post/wrapper_status/pid/running/terminal без ручной подмены phase.
- Evidence: `python3 -m unittest pilot.test_pilot` → OK (208, 13 skipped); `go test -race ./internal/releasebroker` → OK; обе shell fixture → OK; `just check` → passed.
- Next action: Review проверить неизменность retry и process-level evidence CARD-0084.

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

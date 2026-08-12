# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Implemented — terminal результат не подтверждается без надёжной записи.
- Branch: `factory/1cf66d3d-e39-ff94fdcd-f8b7-484a-b92c-01b8f50ecc4e`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 10e00f0bdbeeb9ae7ee965f9c59fd6f71c89bc7a — terminal status публикуется только после успешного persist.
- What changed: При отказе terminal write broker сохраняет последний durable non-terminal status; fresh restart атомарно фиксирует `failed` и не повторяет executor.
- What changed: Реальный process regression подтверждает физическую доставку без receipt, outbox, `mark_final` и owner done при неоднозначной durability.
- Evidence: targeted Pilot state-machine → OK (10); `go test -race ./internal/releasebroker` → OK; installer fixture → PASS; `git diff --check` → passed.
- Next action: Strict Review проверить fail-closed terminal persistence CARD-0084.

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

### 2026-08-12 — Implement

Candidate branch restored and rebased onto current `origin/main`; targeted
state-machine tests passed (10), Go broker race tests passed, and installer
fixture passed. The release fixture was stopped after hanging in the shared
process-fixture environment; full `just check` remains the final verification.

# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Implemented — terminal status становится видимым только после durable sync.
- Branch: `factory/f22a0c29-3e3-9826683e-740`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 4e1c5906a4d5e8571904a132d3113e51e268b8ca — финальная запись broker синхронизируется с диском.
- What changed: Temp record проходит file fsync/close, atomic rename и directory fsync до публикации terminal status; неоднозначный directory-sync откатывается к предыдущей durable записи.
- What changed: Детерминированные sync/close/rename faults и fresh restart подтверждают fail-closed статус и единственный executor; Pilot остаётся выключенным.
- Evidence: broker `-race` → PASS; durability faults ×20 → PASS; Pilot → 213 PASS, 13 skipped; обе shell fixture, `just check`, `just build`, `git diff --check` → PASS.
- Next action: Strict Review проверить candidate `4e1c5906a4d5e8571904a132d3113e51e268b8ca` от base `36ce322e2b6685dd9a87f4d2c947f61538654ae1`.

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

### 2026-08-11 — Implement

Broker now fsyncs every operation temp file and its containing directory before
publishing a terminal result. Deterministic file-sync, close, rename and
directory-sync faults retain the previous durable record; a fresh broker fails
it closed without another executor. Broker race, 20 durability repetitions,
213 Pilot tests, both shell fixtures, `just check`, build and diff all passed.

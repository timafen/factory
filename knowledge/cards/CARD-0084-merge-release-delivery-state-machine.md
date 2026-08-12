# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Implemented — каждый статус release-driver подтверждён до публикации.
- Branch: `factory/cdd9434b-e4e-dc241bb3-b55`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 82e4971b75d0d7b4366036da682bffc4bebfbc52 — release-driver надёжно сохраняет каждый delivery status.
- What changed: Единый helper делает create/write, file fsync, checked close, atomic rename и directory fsync; при ambiguous directory-sync восстанавливает прошлый статус.
- What changed: `launching` и `running` fail-closed до lock/executor; terminal failure не подтверждает success, receipts, outbox или owner completion.
- Evidence: expanded shell fixtures → PASS; broker `-race` → PASS; full Pilot → PASS; `just check`, `just build`, `git diff --check` → PASS.
- Next action: CARD-0086 integration проверить candidate `82e4971b75d0d7b4366036da682bffc4bebfbc52` от base `3183424f924d440b686908f219d0013b7ee8c504`.

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

Correction puts every release-driver phase through one durable status helper:
create/write, file fsync, checked close, atomic rename and directory fsync.
Initial fault injection stops before lock or physical FX; terminal write,
rename, file-sync and dir-sync faults retain `running`, return non-success and
cannot create Pilot completion artifacts or a second executor on recovery.

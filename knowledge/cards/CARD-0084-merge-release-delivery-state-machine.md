# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Implemented — strict-review recovery и privileged launch закрыты fail-closed.
- Branch: `factory/35f73ebf-88b-6a60e59f-fbf`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 8b86b4647cf22ec128d6816ca21b58cccc2ade8e — восстановление merge и запуск release-driver закрыты durable proof.
- What changed: До `gh merge` сохраняется immutable PR/repo/head identity; recovery читает merged PR/commit по номеру, поэтому squash/delete branch не вызывает повторный merge.
- What changed: Broker хранит root-only operation/driver status, открывает process-group gate только после PID/running persistence и не публикует terminal без driver proof; Tarser fail-closed.
- What changed: Driver проверяет owner/mode статуса и все шесть write-fault точек `running`/`failed` сохраняют безопасное `running` без ложного outcome.
- Evidence: full Pilot 217 tests (13 skipped) → PASS; `go test -race ./internal/releasebroker` → PASS; shell/installer fixtures → PASS; `just check`, `just build`, `git diff --check` → PASS.
- Next action: CARD-0086 integration проверить candidate `8b86b4647cf22ec128d6816ca21b58cccc2ade8e` от base `3183424f924d440b686908f219d0013b7ee8c504`.

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

### 2026-08-11 — Implement

Strict-review correction persists immutable PR identity before merge and reads
the authoritative merged PR/commit after crash, including deleted squash
branches. Broker/driver status is root-only and validated; a gated process
group cannot reach release lock before durable PID/running, while unproven
Tarser or failed terminal writes fail closed. Full Pilot (217), broker race,
real shell security/fault fixtures, `just check`, and `just build` passed.

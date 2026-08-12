# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: Implemented and tested; Pilot remains operationally disabled.
- Branch: `factory/82db3b1f-901-430c6234-3d3c`.
- Implementation commit: c61c72ed9224856e2321b2d9713eb1b45b39cfa9 — resume,
  budget and diagnostic repair isolate same-title work by durable `work_id`.
- What changed: owner resume selects only its `work_id` pause, history and metadata;
  title lookup is restricted to legacy records without provenance.
- What changed: root metadata is written after create; budget/repair state uses work ID.
- Evidence: `go test ./internal/controlplane -run Resume -count=1` → PASS;
  `python3 -m unittest pilot.test_pilot -q` → PASS.
- Next action: review and merge; keep Pilot disabled pending its separate release decision.

## LOG

### 2026-08-11 — Specification

Current `main` was inspected. `record_new_works()` currently infers an owner
root from a fresh unknown `[auto]` title, while correction paths such as
`handle_answers()` create ordinary tasks without durable lineage. The new
contract adds nullable `work_id`, `parent_task_id` and `correction_kind` to the
task API/storage, makes explicit provenance authoritative in Pilot, retains a
legacy-only title fallback, and requires a restart storm regression with
exactly one pipeline.

CARD-0086 was absent from fresh `origin/main` and every published `factory/*`
branch when reserved. The prior reservation is owned by concurrent work and
was not reused; old conflicted CARD-0079 remains untouched.

### 2026-08-11 — Implement

Implemented nullable provenance with forward migration 027, transactional API
validation/replay, control-plane child lineage, and provenance-first Pilot
grouping. Review and Verify storm regressions survive a durable restart with
one work/pipeline, no second Triage, and one prevented-root event. Full Go tests,
all 204 Pilot tests, and the Go build passed; Pilot enablement was not changed.

### 2026-08-11 — Implement

Strict Review corrections landed in
`aa05c7eb3c01e665609bc847b0f493f35edd10f9`. Migration 027 now fails before
ALTER and without ledger advance on a 025 database, then upgrades/reopens after
the exact 026 schema is present. Parameterized Review/Verify tests use the real
answer-resume and cycle paths across persisted state recreation, ending in one
root/work/pipeline, merge and owner completion. Crash-boundary tests prove one
durable outbox event. Full Go tests passed with the exact pending 026 migration
fixture; all 204 Pilot tests and the final-tree build passed. This branch is
intentionally unmergeable/unreleasable until CARD-0085/026 reaches `main`, and
Pilot remains disabled.

### 2026-08-11 — Release-unblock correction

CARD-0085 migration 026 is now in `origin/main` at
`60cba840f39a453862c1c0f87f261fd453b09688`; the clean CARD-0086 code was
cherry-picked onto that base. The focused provenance migration tests, all 204
Pilot tests, `go test ./...`, `go build ./...`, and the whitespace diff check
passed. The 027 dependency guard remains atomic, and Pilot remains disabled.

### 2026-08-11 — Implement

On `factory/016c61a8-e4d-be2c802c-a1a`, based on fresh
`origin/main` `60cba840f39a453862c1c0f87f261fd453b09688`, implementation
`4f36ccb2af718e95b0ff5318864f34940d3102c6` replaces title-keyed Pilot
artifact/delivery/lifecycle state with `work_id` where provenance exists. Two
same-title corrections now preserve their own branches through restart, Review,
Verify, merge and archive; a legacy parent and provenance child share one next
stage without a duplicate Triage or Specification. Focused regressions, all 206
Pilot tests, migration-027 dependency test, full Go tests/build and diff check passed.

### 2026-08-11 — Implement

Implementation commit: c61c72ed9224856e2321b2d9713eb1b45b39cfa9 — owner resume
now uses durable `work_id`, preserving a separate same-title pause and task
history. Root metadata is recorded after creation, and budget/diagnostic repair
storage follows the same ID. Focused resume Go tests and the Pilot unit suite pass.

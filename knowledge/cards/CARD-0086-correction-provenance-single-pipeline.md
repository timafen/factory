# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: BLOCKED: final rebased Pilot provenance storm test has 3 errors.
- Branch: `factory/ffb2f1bd-e35-41637e93-24a` (rebased onto current `main`).
- Implementation commit: a65fb2e82af6e752555a02abbd5557283868e7e9 — durable
  `work_id` isolation for same-title artifact, delivery and lifecycle state.
- Evidence: pre-rebase project check and focused provenance API/migration passed;
  after rebase, three storm paths fail while serializing a `MagicMock` merge intent.
- Next action: implementation fixes the rebased merge-intent test contract, then Verify reruns.

## LOG

### 2026-08-11 — Verify

| Criterion | Evidence | Result |
| --- | --- | --- |
| Provenance create/replay/list/detail and parent deletion | focused `go test` control-plane provenance set | PASS |
| Migration 027 dependency on 026 and atomic reopen | focused migration test | PASS |
| Same-title correction after restart creates no duplicate root | final `CorrectionProvenanceStormTests` (7 tests) | BLOCKED: 3 errors |
| Whole project and build | `just check`; `go build ./...` | PASS |
| Delivery hygiene | rebase on current `main`; `git diff --check` | PASS |

The rebase adopted the current main merge-intent path. Three corrections now fail
because its state persistence receives a mocked non-serializable link. This is
an implementation defect in the rebased result, not an infrastructure failure.

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

CARD-0086 was re-integrated onto fresh `origin/main`
`36ce322e2b6685dd9a87f4d2c947f61538654ae1`, preserving CARD-0087’s fresh
Review-base logic while applying the provenance, migration 027 and Pilot work.
Focused same-title/legacy restart and migration checks passed; full Pilot (209
tests), `go test ./...`, `go build ./...` and whitespace diff check passed.
Pilot remains disabled; the implementation is `55cfcdabaafa8ddeb9b91a8ed70d75be5e51b3b3`.

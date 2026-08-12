# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: Implemented and tested on fresh `origin/main`; ready for Review.
- Branch: `factory/39575a1d-a1c-59153c04-7c9`.
- Implementation commit: fbfd67350c488a07313faef4e983b4056cbe5fc7 — rescue,
  DIAG and diagnostic-repair state is isolated by durable `work_id`.
- What changed: same-title work no longer shares automatic-return limits,
  diagnosis history, repair cancellation, or one-time resume state.
- What changed: diagnostic evidence and active-run selection stay within the
  originating work; legacy title-only records remain readable.
- Evidence: 44 post-rebase Pilot regressions and five targeted control-plane
  provenance tests pass; full Pilot passed 223 tests before the final rebase.
- Evidence: `go build ./...` passes; broad Go tests pass outside pre-existing
  `internal/worker` timeout failures documented in this LOG.
- Next action: repeat independent Review on this delivered branch.

## LOG

### 2026-08-11 — Implement

Rebased merge recovery no longer writes a mocked/non-JSON generation into the
durable merge intent.  A no-adapter repository closes after its durable merge,
while a real adapter may persist only its string generation ID.  The receipt
now carries `work_id`, so two corrections with the same display title archive
independently.  Focused control-plane provenance tests and the seven restart
storm tests passed; Pilot enablement was left unchanged.

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

### 2026-08-12 — Verify

| Acceptance evidence | Command/check | Observed result |
|---|---|---|
| Legacy root/API compatibility; child validation; replay and SQLite migration | `go test ./internal/controlplane -run '^(TestTaskProvenanceValidationAndReplay\|TestTaskProvenancePersistsAcrossReopenAndParentDelete\|TestTaskProvenanceMigrationUpgradesLegacyDatabase\|TestTaskProvenanceHTTPCompatibilityAndLogging\|TestResumePausedWorkUsesVerdictActionForReviewAndVerify)$' -count=1` | PASS (five targeted tests after rebase) |
| Review/Verify corrections retain one work and pipeline through restart; title cannot override provenance; prevented event is idempotent | `python3 -m unittest -v pilot.test_pilot.CorrectionProvenanceStormTests` | PASS (5 tests) |
| Adjacent legacy Pilot behavior | `python3 -m unittest -v pilot.test_pilot` | PASS (204 tests) |
| Build and broad project checks | `FACTORY_BUILD_DIR=/tmp/card0086-build.hUIIBy just build`; `just check` | Build PASS; checks reached all Go tests, where unrelated `internal/worker/TestTimeoutStopsIgnoringProcessGroup` failed because the task timed out before process start |
| Delivery hygiene | fixed-SHA diff, implementation ancestry, `git diff --check`, clean status | Implementation commit changes code outside the card; no whitespace/debug/stray-file findings |

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

### 2026-08-12 — Implement

Automatic rescue counters, senior diagnosis and durable diagnostic repairs now
use `work_storage_key(base, work_id)`. Two works with the same title can each
spend their own retry allowance, cancel only their own looping task and resume
once after restart. Post-rebase Pilot regressions passed 44 tests, including
the two new same-title cases; five focused control-plane provenance tests and
the Go build passed. The broad Go run remained red only in pre-existing
`internal/worker` timing tests outside this change; Pilot stays disabled.

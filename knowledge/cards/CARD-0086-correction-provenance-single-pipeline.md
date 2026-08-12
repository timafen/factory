# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: Implemented and tested on fresh `main`; ready for repeated Review.
- Branch: `factory/edc1f5b1-410-a19e0c85-755`.
- Implementation commit: a042e43239d4d5dcf787cdf11d3e80464065a1b7 — real-restart correction proof, migration dependency guard, and durable duplicate-root outbox.
- What changed: migration 027 validates migration 026 and migration ledger
  versions come from filenames; Review/Verify corrections survive recreated state.
- What changed: prevented duplicate roots remain as stable-ID durable outbox
  events across every tested crash boundary.
- Evidence: focused Go migration test PASS; two restart/outbox tests PASS;
  all 225 Pilot tests PASS; `go test -timeout 5m ./...` PASS; build PASS.
- Next action: repeat Review against this branch and its exact published SHA.

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

### 2026-08-12 — Verify

| Acceptance evidence | Command/check | Observed result |
|---|---|---|
| Legacy root/API compatibility; child validation; replay and SQLite migration | `go test ./internal/controlplane -run '^(TestTaskProvenanceValidationAndReplay\|TestTaskProvenancePersistsAcrossReopenAndParentDelete\|TestTaskProvenanceMigrationUpgradesLegacyDatabase\|TestTaskProvenanceHTTPCompatibilityAndLogging\|TestResumePausedWorkUsesVerdictActionForReviewAndVerify)$' -count=1` | PASS (five targeted tests after rebase) |
| Review/Verify corrections retain one work and pipeline through restart; title cannot override provenance; prevented event is idempotent | `python3 -m unittest -v pilot.test_pilot.CorrectionProvenanceStormTests` | PASS (5 tests) |
| Adjacent legacy Pilot behavior | `python3 -m unittest -v pilot.test_pilot` | PASS (204 tests) |
| Build and broad project checks | `FACTORY_BUILD_DIR=/tmp/card0086-build.hUIIBy just build`; `just check` | Build PASS; checks reached all Go tests, where unrelated `internal/worker/TestTimeoutStopsIgnoringProcessGroup` failed because the task timed out before process start |
| Delivery hygiene | fixed-SHA diff, implementation ancestry, `git diff --check`, clean status | Implementation commit changes code outside the card; no whitespace/debug/stray-file findings |

### 2026-08-12 — Implement

Republished the strict restart proof on fresh `main` after migration 026 landed.
The focused migration check passed, Review and Verify both completed one pipeline
after persisted-state recreation, and crash-boundary outbox checks converged.
The full 225-test Pilot suite, all Go tests, and `go build ./...` passed; the
restart fixture was updated to complete through the current release broker path.

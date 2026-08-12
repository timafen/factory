# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: Implemented and targeted checks pass; ready for Review.
- Branch: `factory/0c8206c2-db3-5816087b-ae8`.
- Implementation commit: 2e0190c3ec2db82baadb16a76b120fbaacc9cc17 — same-title resume, outbox, and merge recovery remain isolated by `work_id`.
- What changed: same-title work remains separated by durable `work_id`, including
  HTTP resume requests that omit `title`; Review keeps pinned SHA comparison and
  merge keeps persist-before-action recovery across restart.
- Evidence: targeted control-plane test PASS; full `pilot.test_pilot` PASS; build
  PASS. `just check` reached the broad suite but unrelated control-plane/worker
  packages timed out after five minutes under concurrent host load.
- Next action: review the fixed-SHA Review, merge recovery, and work-only resume paths.

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

Restored the current `main` protections removed by the earlier candidate:
Review compares an isolated pinned base/candidate snapshot, and merge intent is
persisted before the external merge and recovered after restart. Resume now
accepts `work_id` without `title`, derives the selected pipeline title, and a
same-title regression proves that only the requested work resumes. The targeted
control-plane test, full Pilot suite, and build passed. The one full `just check`
run timed out in unrelated control-plane and worker tests amid concurrent host
load; the task-specific control-plane test passed independently in 12.7 seconds.

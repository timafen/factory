# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: Verified PASS — awaiting human merge; Pilot remains operationally disabled.
- Branch: `factory/d1212c45-6d0-3e6223b8-1f8`.
- Implementation commit: b886a12937ad668cf769d061374f93099c37d9f4 — durable task provenance and correction-safe single-pipeline Pilot grouping.
- What changed: migration 027 and the task API persist root/parent/correction
  identity; every direct continuation path inherits the original `work_id`.
- What changed: Pilot uses explicit provenance before legacy title fallback and
  durably journals one `pilot_duplicate_root_prevented` event per correction.
- Evidence: all 204 Pilot tests and the build pass; five post-rebase provenance
  storm tests and five control-plane provenance/API/migration tests pass. The
  full `just check` found one unrelated flaky worker timeout test (documented below).
- Next action: human merges `factory/d1212c45-6d0-3e6223b8-1f8`.

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

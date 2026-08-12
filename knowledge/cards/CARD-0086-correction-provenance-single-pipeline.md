# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: Verified PASS — awaiting human merge; Pilot remains operationally disabled.
- Branch: `factory/8493f4e1-e7f-d0bef795-c9b` (base `origin/main` `be3aece4f84b9432d6ffc0e77d4e6735b5b99140`).
- Implementation commit: f12fc67fc2d1497ad348dcdf77281f82dfeb3146 — same-title resume, Review and Verify remain isolated by durable `work_id` after rebase.
- What changed: resume lookup and every Pilot delivery path retain the originating
  work identity; the restart regression covers both works under bounded polling.
- Evidence: isolated controlplane/worker packages pass on both main and candidate;
  full Go, static, UI (161), Pilot (232), tooling, launcher and build checks pass.
- Next action: human merges `factory/8493f4e1-e7f-d0bef795-c9b`.

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

Rebased the work-ID isolation delivery onto `origin/main`
`be3aece4f84b9432d6ffc0e77d4e6735b5b99140` and reconciled Pilot's bounded
terminal-task traversal with the two-work restart regression. The previously
reported recovery/polling timeout was classified by isolated verbose runs:
both packages pass on fresh main and candidate, and the full Go suite passes
when allowed to finish. Targeted provenance tests, 232 Pilot tests, 161 UI
tests, static checks, tooling, launcher and the complete build passed.

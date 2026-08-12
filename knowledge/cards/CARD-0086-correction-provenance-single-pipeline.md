# CARD-0086 — Одна корректировка не создаёт второй конвейер

Implementation commit: f3dbc48009e2314db1ee21538b49f506ba065e47 — возобновление одноимённых работ строго по `work_id`.

## HEAD

- Status: Implemented and rebased on current `origin/main`; awaiting review.
- Branch: `factory/5925ce7b-cdf-02966af7-5bd`.
- Implementation commit: f3dbc48009e2314db1ee21538b49f506ba065e47 — resume lookup uses the durable `work_id`.
- What changed: the control plane and frontend pass `work_id` through resume;
  Pilot keeps matching titles in separate durable pipelines and artifacts.
- Evidence: targeted Go provenance tests, 8 Pilot isolation scenarios, 19 web
  tests, and the web production build pass after the rebase.
- Next action: review the rebased change and merge it.

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

### 2026-08-12 — Verify

| Acceptance evidence | Command/check | Observed result |
|---|---|---|
| Root compatibility, inherited provenance, atomic validation/replay, reopen and 025→027 migration rules | `just check` (Go/static portion, pinned candidate) | PASS; all Go packages passed, including controlplane provenance and migration tests |
| Review/Verify correction, title-independent classification, one pipeline after restart, durable duplicate-root event | `python3 -m unittest -v pilot.test_pilot.CorrectionProvenanceStormTests` | PASS (8 tests) |
| Legacy fallback and adjacent Pilot behavior remain compatible | `python3 -m unittest -v pilot.test_pilot` | PASS (232 tests, 13 skipped) |
| UI/API presentation and real-server browser behavior | `just ui-check`; `just test-browser` after `just ui-install` | PASS (161 UI tests; browser suite passed) |
| Worker coordination, release artifacts, tooling, launcher and binaries | `just test-worker-race`; `just test-release`; `just test-tooling`; `just test-launcher`; `FACTORY_BUILD_DIR=/tmp/card0086-build-82Q7aw just build` | PASS |
| Delivery identity and hygiene | pinned `d9dcf3c…...0abbb976…`; implementation ancestry/code check; `git diff --check`; clean status | PASS; non-empty 19-file delivery, implementation commit changes code outside the card, no whitespace or stray-file findings |

The initial UI/browser invocation stopped because a clean worktree had no
`web/node_modules` (`tsc: not found`). After the repository-prescribed
`just ui-install`, only the unexecuted UI/browser checks were rerun and passed.

### 2026-08-12 — Implement

Rebased the `work_id` isolation change onto current `origin/main`; the only
conflict was a generated frontend bundle, rebuilt from the reconciled sources.
Targeted control-plane provenance tests, eight durable Pilot isolation scenarios,
nineteen frontend tests, and the production frontend build pass.

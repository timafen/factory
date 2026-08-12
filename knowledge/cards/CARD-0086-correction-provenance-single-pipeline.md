# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: Implemented and tested on current `main`; Pilot remains operationally disabled.
- Branch: `factory/88d06a21-24e-825e0559-1fc` (base `origin/main`
  `a10c16175cc87e3aff0ef131e3848a00a7a5b074`).
Implementation commit: 8d6fbd95d79800a5fd2c64bb90eddbbb59265541 — strict `work_id` isolation is preserved through resume, Review and safe delivery.
- What changed: same-title pauses, metadata, history, Review state and delivery
  artifacts remain isolated by `work_id`; title fallback is legacy-only.
- Evidence: post-rebase provenance/release/UI/typecheck targets → PASS; prior
  final tree full Pilot 222 tests (13 skipped), UI 161/161, HTTPS Chromium
  21/21, full Go, lint and builds → PASS.
- Next action: review and merge this correction while keeping Pilot disabled.

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

Rebased the complete same-title isolation onto `origin/main`
`62832535c96b409ef7736440b5c95bca5e8a0d2a`, retaining the merged correction
provenance and process-based release recovery. Merge intents, merge journals,
delivery waits and final receipts now carry `work_id`; the restart regression
uses the real safe-release path and proves two identical titles retain separate
receipts. Post-rebase targeted Pilot (7), control-plane provenance/resume, UI
(18) and TypeScript checks passed. Before the final base movement, full Pilot
(222 tests, 13 skipped), UI (161), HTTPS Chromium (21), full Go, lint and both
builds passed. Pilot remains operationally disabled.

### 2026-08-12 — Implement

Final no-conflict rebase onto `origin/main`
`a10c16175cc87e3aff0ef131e3848a00a7a5b074` retained the owner-attribution
correction from PR #149 and the complete `work_id` isolation. The implementation
commit is `8d6fbd95d79800a5fd2c64bb90eddbbb59265541`; the seven provenance storm tests,
the required TypeScript command and the three-dot whitespace check passed again.

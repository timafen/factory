# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: BLOCKED: required rebase onto fresh `origin/main` conflicts in `pilot/pilot.py`; Pilot remains operationally disabled.
- Branch: `factory/69214378-750-e950d8ba-0df` (base `origin/main`
  `36ce322e2b6685dd9a87f4d2c947f61538654ae1`).
- Implementation commit: 4640ac31411c15b870c42da8860aa898bd282e44 — resume and Review durable state are isolated by `work_id`.
- What changed: Work UI and `/api/v1/works/resume` pass `work_id`; pause,
  metadata, history and child selection no longer merge same-title works.
- What changed: Review promises, areas, return limits, dirty/gate state and
  delivery artifacts use `work_id`; title fallback remains legacy-only.
- Evidence: same-title resume isolation and legacy fallback passed in the
  control-plane target; full Go exposed only pre-existing configuration schema
  and worker-integration failures outside this change.
- Next action: resolve the `pilot/pilot.py` rebase conflict against fresh `main`,
  then repeat verification; keep Pilot disabled pending its separate safe
  release-state-machine decision.

## LOG

### 2026-08-11 — Verify

| Criterion | Command/check | Observed result |
| --- | --- | --- |
| Resume selects one same-title pipeline by durable identity | Targeted control-plane tests for work-ID isolation and legacy fallback | Passed: resuming the first `work_id` left the second pause and history intact; legacy title-only resume remains supported. |
| Review state stays separated by durable identity | Three same-title Pilot regressions with `PYTHONPATH=.` | Passed: independent work IDs retain separate Review facts, artifacts, restart state and merge lifecycle. |
| Whole-repository regression check | Go, build, Pilot and web test commands from a clean tree | Go ran 389–399 s and failed in unrelated `TestPilotConfigExampleMatchesServerSchema` and four worker integration timeouts; Pilot discovery used an invalid import context and web dependencies were absent (`eslint: not found`). |
| Fresh-main delivery | `git fetch origin main && git rebase origin/main` | Blocked at the first replayed implementation commit by a content conflict in `pilot/pilot.py`; rebase was aborted, leaving the delivered implementation unchanged. |

The implementation diff is whitespace-clean and the recorded implementation
commit is an ancestor of the delivered branch. Verification cannot approve a
merge until the fresh-main conflict is resolved and the suite is rerun.

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

### 2026-08-11 — Implement

Strict Review blockers were corrected end-to-end on a new branch. Resume now
uses explicit `work_id` through the Work UI, API pause lookup, metadata,
pipeline history and child selection; a two-pause regression proves the other
same-title work stays paused and keeps its own history. The real Review gate
regression proves promises, areas, return limits, gate/dirty decisions and
delivery artifacts do not cross between two same-title work IDs, while legacy
title fallback remains covered. Focused HTTPS browser, UI/API/Pilot and
migration tests passed; full Pilot passed 210/210, full UI 159/159, lint and all
builds passed. Full Go has only the separately tracked current-main failure
`TestPilotConfigExampleMatchesServerSchema`; all Go tests pass when excluding
that exact test. Pilot remains disabled.

# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: Corrected and fully tested on current `main`; Pilot remains operationally disabled.
- Branch: `factory/9237f495-61a-a45beb40-508` (base `origin/main`
  `3183424f924d440b686908f219d0013b7ee8c504`).
- Implementation commit: 0ba694a163b0840ed9ec847f08f8b3b170a80b41 — Plan, epic, receipts, budgets and history branches are isolated by `work_id`.
- What changed: Plan/epic completion and root metadata require matching
  provenance; title fallback is limited to rows where both sides are legacy.
- What changed: work spend, budget/stop state and history branch selection use
  the stable work key, with concurrent same-title regressions for both roots.
- Evidence: focused Pilot 32/32 and provenance/migration Go → PASS; full Pilot
  214/214, UI 160/160, HTTPS browser 21/21, full Go, lint/build/dist/diff → PASS.
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

### 2026-08-11 — Implement

Re-integrated CARD-0086 onto current `origin/main`
`3183424f924d440b686908f219d0013b7ee8c504`. Provenance, migration 027,
Pilot durable isolation and UI/API resume were preserved, while CARD-0087's
fresh-review behavior and the PR #135 Pilot config fix remain unchanged.
Focused API/UI/Pilot/migration and HTTPS Chromium checks passed; full Pilot
passed 210/210, fresh-main UI passed 160/160, `umask 077; go test ./...`, lint,
Go/UI builds and diff checks passed. Pilot remains disabled.

### 2026-08-11 — Implement

Strict Review's remaining title-only paths were corrected on the new branch.
Plan and epic completion, subtask/task/merge receipts, root `note_work`, work
spend, budget/stop state and history branch lookup now use the stable `work_id`;
only two genuinely provenance-free legacy records may fall back to title.
Concurrent same-title regressions exercise real Plan, epic, merge and budget
state: work-a cannot complete, charge, stop, or choose a branch for work-b.
Focused Pilot passed 32/32 and provenance/API/migration Go checks passed; full
Pilot passed 214/214, UI 160/160, HTTPS Playwright 21/21, full
`umask 077; go test ./...`, lint, Go/UI builds, dist and diff checks passed.
Pilot remains disabled.

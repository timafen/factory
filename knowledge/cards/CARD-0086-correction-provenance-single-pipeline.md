# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: Verified PASS — awaiting human merge; Pilot remains operationally
  disabled.
- Branch: `factory/31b80853-0f0-095f6283-3e1`.
- Implementation commit: 7cd603288a2e666cb261248649fa3bba871f744a — migration dependency safety, real restart full-cycle proof, and durable duplicate-root outbox.
- Evidence: clean-cache `go test ./...` → PASS; full Pilot suite → PASS
  (209 tests); `go build ./...` and whitespace check → PASS. The provenance
  API/migration tests and the restart-storm/outbox tests cover all ten
  acceptance criteria.
- Next action: human reviews and merges the correction; Pilot stays disabled
  until its separate safe release-state-machine decision.

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

### 2026-08-11 — Verify

| Acceptance criterion | Command/check | Observed result |
| --- | --- | --- |
| 1–3: root/child provenance, validation, replay, persistence and legacy rows | `go test ./...` including provenance store and HTTP tests | PASS |
| 4–6: Review/Verify correction stays one pipeline across restart | `python3 -B -m unittest -v pilot.test_pilot` including `CorrectionProvenanceStormTests` | PASS; both correction kinds complete Review, Verify, merge and owner completion with one root |
| 7: prevented-root durable event is idempotent through crash boundaries | full Pilot suite, `test_duplicate_root_outbox_converges_at_every_crash_boundary` | PASS; one stable outbox event before/after restart and acknowledgement |
| 8–9: legacy fallback and atomic 025/026/027 migration dependency | full Go suite including provenance migration test | PASS |
| 10: Pilot remains disabled | code/card review; no enablement change in diff | PASS |
| Adjacent build and patch hygiene | `go build ./...`; `git diff --check origin/main...HEAD` | PASS |

Clean-cache full verification completed: `go test ./...` (PASS),
`python3 -B -m unittest -v pilot.test_pilot` (209 tests, PASS), and
`go build ./...` (PASS). The tree had no unrelated changes before the card
update; the implementation commit is an ancestor and changes code outside
`knowledge/cards/`.

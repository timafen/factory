# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: Implemented and fully tested; Pilot remains operationally disabled.
- Branch: `factory/d1212c45-6d0-3e6223b8-1f8`.
- Implementation commit: 86a0ff83e39cc84c7a9e49e4ee061e675a5cf1cb — durable task provenance and correction-safe single-pipeline Pilot grouping.
- What changed: migration 027 and the task API persist root/parent/correction
  identity; every direct continuation path inherits the original `work_id`.
- What changed: Pilot uses explicit provenance before legacy title fallback and
  durably journals one `pilot_duplicate_root_prevented` event per correction.
- Evidence: `go test ./...` → PASS; `python3 -m unittest -v pilot.test_pilot`
  → PASS (204 tests); `go build ./...` → PASS.
- Next action: deploy control plane then Pilot binary while Pilot stays disabled,
  and smoke-test provenance before any separate enablement decision.

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

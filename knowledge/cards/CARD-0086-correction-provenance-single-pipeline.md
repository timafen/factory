# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: Specification ready — implementation pending.
- Specification: `knowledge/specs/correction-provenance-single-pipeline.md`.
- Scope: durable task/work provenance, correction-safe Pilot discovery,
  compatibility migration, prevented-root event and storm regression.
- Owner impact: Review/Verify correction continues and closes the original work
  without launching or charging for another five-stage pipeline.
- Rollout gate: Pilot remains disabled until this change and separate safe
  release logic are deployed and smoke-tested.
- Next action: implement the specification without reusing the conflicted old
  CARD-0079 branch.

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

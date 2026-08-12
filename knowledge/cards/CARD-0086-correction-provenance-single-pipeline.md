# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: Implemented — awaiting Review.
- Branch: `factory/d40c77cd-34c-8ddd7926-bf0`.
- Implementation commit: c9c10250e80beaa6b12b8dcd711ee948e0a1aab9 — сохранено
  происхождение задач для корректировок.
- What changed: control plane сохраняет `work_id`, родителя и причину
  корректировки; Pilot не принимает явного потомка за новый root.
- Evidence: `go test ./internal/controlplane` → PASS; `python3 -m unittest -v
  pilot.test_pilot` → PASS.
- Next action: Review проверяет полный contract provenance и storm/restart cases.

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

### 2026-08-12 — Implement

Добавлена additive migration 027 и API/storage provenance для корней и
потомков, включая replay и validation. Pilot исключает явные correction-задачи
из root discovery и передаёт parent в обычном продолжении, resume и watcher.
`go test ./internal/controlplane` и `python3 -m unittest -v pilot.test_pilot`
завершились успешно.

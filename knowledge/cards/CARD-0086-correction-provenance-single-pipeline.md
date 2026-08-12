# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

- Status: Implemented — ready for Review.
- Branch: `factory/a904c45d-6fd-edfbfaf9-d29`.
- Implementation commit: af3363c0dd731ae18f1f890bcdaf096c3bf55b32 — Pilot проверяет Review-корректировку прямо по полному ответу API без ручной подстановки provenance.
- What changed: регрессионный сценарий получает корректировку из
  `create_child_task()` через API, проверяет возвращённые `work_id`,
  `parent_task_id`, `correction_kind` и дважды передаёт тот же объект в Pilot.
- Evidence: `CorrectionProvenanceStormTests` — PASS, 7 tests;
  `TestTaskProvenanceHTTPCompatibilityAndLogging` — PASS; `just build` — PASS.
- Next action: Review проверяет целевой сценарий и изменения относительно свежей `main`.

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

Отдельный сквозной тест создаёт Review-корректировку через дочерний builder,
передаёт ответ API обратно в обнаружение Pilot и повторяет его после условного
рестарта. Подтверждено: сохраняется только исходный `work_id`, а для
корректировки остаётся единственная защитная запись; `CorrectionProvenanceStormTests` — 7 PASS.

### 2026-08-12 — Implement

После замечания Review сценарий больше не собирает ответ корректировки вручную:
он вызывает клиентский путь `create_child_task()` → `create_task()` → API,
берёт неизменённый `created["task"]`, проверяет в нём `work_id`, родителя и вид
корректировки, затем дважды отдаёт этот объект в `record_new_works()`. Семь
`CorrectionProvenanceStormTests`, серверный тест provenance API и сборка прошли.

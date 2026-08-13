# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

Implementation commit: afd3d9b7acce926389aa79f5eed1b85e4e8a39a9 — устойчивое provenance и реальный перезапуск Review/Verify-конвейера Pilot.
- Status: Verified PASS — awaiting human merge.
- Branch: `factory/ed7ee7b4-87a-19b13995-d52`.
- What changed: проверка полного цикла теперь запускает первый и второй Pilot
  в разных Python-процессах; второй получает только устойчивые JSON-фикстуры и state.
- What changed: корректировка с изменённым заголовком продолжает тот же work_id
  через Review и Verify до финального merge/terminal verdict, без нового root.
- Evidence: `go test ./...` — PASS; `python3 -m unittest -v pilot.test_pilot` —
  230 OK (13 skipped); реальный subprocess-рестарт Review/Verify — 7 OK.
- Next action: Человеку проверить evidence и принять решение о merge.

## LOG

### 2026-08-12 — Verify

| Acceptance evidence | Command/check | Observed result |
|---|---|---|
| Корректировка Review и Verify не создаёт второй конвейер после настоящего рестарта процесса Pilot | `python3 -m unittest -v pilot.test_pilot.CorrectionProvenanceStormTests` | PASS: 7 tests; subprocess fixture восстанавливает durable state и завершает один pipeline. |
| Provenance хранится и API/миграция сохраняют обратную совместимость | `go test ./internal/controlplane -run '^(TestTaskProvenanceValidationAndReplay\|TestTaskProvenancePersistsAcrossReopenAndParentDelete\|TestTaskProvenanceMigrationUpgradesLegacyDatabase\|TestTaskProvenanceHTTPCompatibilityAndLogging\|TestResumePausedWorkUsesVerdictActionForReviewAndVerify)$' -count=1` | PASS: 5 tests. |
| Регрессии Pilot рядом с обработкой конвейеров | `python3 -m unittest -v pilot.test_pilot` | PASS: 230 tests, 13 skipped. |
| Полная проектная проверка | `go test ./...` | PASS; все Go packages, включая `internal/controlplane` и `internal/worker`. |
| Гигиена поставки | pinned-SHA diff, `git diff --check`, чистый checkout | PASS; implementation commit является предком ветки и меняет код вне карточки. |

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

Republished the strict restart proof on fresh `main` after migration 026 landed.
The focused migration check passed, Review and Verify both completed one pipeline
after persisted-state recreation, and crash-boundary outbox checks converged.
The full 225-test Pilot suite, all Go tests, and `go build ./...` passed; the
restart fixture was updated to complete through the current release broker path.

### 2026-08-12 — Implement

Rebased the restart proof onto `fc8548f244fe1eb2a1c653c224de668844e2f1a3`
and preserved the current Pilot release flow. Because migration 027 is already
published, its dependency check moved to the new side-effect-free migration 028;
the regression rejects databases missing either prerequisite schema. Five
focused Go tests, six correction-storm tests, all 229 Pilot tests, Go vet,
Python compilation, and the binary build passed.

### 2026-08-12 — Implement

Replaced the same-interpreter restart simulation with subprocess evidence. Both
Review and Verify correction discovery now terminate one Pilot interpreter and
restore from durable files in another while retaining exactly one pipeline.
Each of the four outbox crash boundaries exits a subprocess with code 86 and
converges in a fresh process. Seven focused tests, all 230 Pilot tests (13
skipped), all Go tests, Go vet, Python compilation, and the Go build passed.

### 2026-08-12 — Implement

Пересобрано от свежего `origin/main`: перенесены только provenance, migration 028,
outbox и их целевые тесты. Первый subprocess создаёт и устойчиво фиксирует
корректировку, второй чисто импортирует Pilot и завершает её Review/Verify до
final verdict и merge, читая только JSON state/API-фикстуры. `python3 -m unittest
pilot.test_pilot.CorrectionProvenanceStormTests` дал 7 OK; `go test ./internal/controlplane`
и `python3 -m py_compile pilot/test_pilot.py` прошли.

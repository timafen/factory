# CARD-0086 — Одна корректировка не создаёт второй конвейер

## HEAD

Implementation commit: 8b189f33b8bf3d11fccb5d8e35424b32090b9a9b — внешний merge завершает исходное ожидание в том же перезапущенном Review/Verify-конвейере.
- Status: Implemented; повторный Review уже дал APPROVE, ожидается Verify.
- Branch: `factory/b59bd67b-e7c-d1816795-613`.
- What changed: внешний репозиторий получает устойчивую merge-only generation;
  подтверждённый merge завершает её без неподдерживаемого deploy-адаптера.
- What changed: subprocess-регрессия проводит Review и Verify через настоящий
  рестарт до одного merge, terminal verdict и отправленного owner-события.
- Evidence: `CorrectionProvenanceStormTests` — PASS (11 tests);
  `go test ./internal/controlplane -count=1` — PASS; `git diff --check` — PASS.
- Next action: запустить Verify на этой ветке и при PASS передать на merge.

## LOG

### 2026-08-12 — Verify

| Acceptance evidence | Command/check | Observed result |
|---|---|---|
| Корректировка Review и Verify не создаёт второй конвейер после настоящего рестарта процесса Pilot | `python3 -m unittest -v pilot.test_pilot.CorrectionProvenanceStormTests` | PASS: 7 tests; subprocess fixture восстанавливает durable state и завершает один pipeline. |
| Provenance хранится и API/миграция сохраняют обратную совместимость | `go test ./internal/controlplane -run '^(TestTaskProvenanceValidationAndReplay\|TestTaskProvenancePersistsAcrossReopenAndParentDelete\|TestTaskProvenanceMigrationUpgradesLegacyDatabase\|TestTaskProvenanceHTTPCompatibilityAndLogging\|TestResumePausedWorkUsesVerdictActionForReviewAndVerify)$' -count=1` | PASS: 5 tests. |
| Регрессии Pilot рядом с обработкой конвейеров | `python3 -m unittest -v pilot.test_pilot` | PASS: 230 tests, 13 skipped. |
| Полная проектная проверка | `go test ./...` | PASS; все Go packages, включая `internal/controlplane` и `internal/worker`. |
| Гигиена поставки | pinned-SHA diff, `git diff --check`, чистый checkout | PASS; implementation commit является предком ветки и меняет код вне карточки. |

The rebase adopted the current main merge-intent path. Three corrections now fail
because its state persistence receives a mocked non-serializable link. This is
an implementation defect in the rebased result, not an infrastructure failure.

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

### 2026-08-14 — Implement

После подтверждённого APPROVE работа перенесена на свежий `origin/main` без
новой задачи или ветки. Устаревшие изменения опубликованной миграции 027 сняты;
итоговая поставка содержит только external merge-only completion и process-level
проверку единого Review/Verify-конвейера. Все 11 `CorrectionProvenanceStormTests`
и пакет `internal/controlplane` прошли, Python-файлы компилируются, diff чист.

# CARD-0128 — Денежный сторож вмешивается после пятого круга

Implementation commit: ddd2cc291eefa04c2ec2e48e58bf254eeb92d33e — ремонты и диагностика изолированы по `work_id`

## HEAD

Status: Verified PASS — awaiting human merge.
Branch: `factory/b90560c1-043-0f15c8f1-e4c`.
Implementation commit: ddd2cc291eefa04c2ec2e48e58bf254eeb92d33e — сторож изолирует ремонт, лимит и диагностическую историю по `work_id`.
What changed: `begin_diag_repair()` получает `work_id`, отбирает активные задачи через `same_task_work()` и хранит ремонт отдельно для каждой работы. `recent_stage_text()` и поиск ветки используют ту же изоляцию.
Evidence: pinned base `73f4edce272cb113607540412425d842158e2b81`, candidate `28b68ee16869c55e122e33406341c307b461d83e`; target tests 20/20, Go tests passed, binaries built, `py_compile` passed. НАХОДКА: полный Python-модуль — 255/257, два падения в независимом `CorrectionProvenanceStormTests` при restart.
One next action: human merge the verified implementation branch.

## LOG

### 2026-08-13 — Implement

Исправлено сопоставление ранней диагностики с современными задачами: вместо владельческого заголовка счётчик получает задачу с устойчивым `work_id`.
Добавлены регрессии на срабатывание ровно на пятом круге и изоляцию одноимённых работ; 19 целевых сценариев прошли, синтаксическая компиляция завершилась с кодом 0.

### 2026-08-13 — Implement

После замечаний Review ремонт, лимит диагностики и диагностическая история переведены с заголовка на `work_id`; старые задачи без идентификатора сохраняют прежнее сопоставление по заголовку.
Добавлен немоканный регрессионный путь `diag_sweep()` → `begin_diag_repair()` для двух одновременных одноимённых работ: каждая отменяется и сохраняется отдельно, а чужая история не попадает в разбор.
`python3 -m unittest pilot.test_pilot.DiagnosisRepairTests -v` — 20/20, `OK`; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` — код 0.

### 2026-08-13 — Verify

| Acceptance criterion | Check | Observed result |
| --- | --- | --- |
| Сторож вмешивается по устойчивой работе и раньше лимита затрат | `python3 -m unittest pilot.test_pilot.DiagnosisRepairTests -v` | 20/20, `OK`; проверки пятого круга, повторного лимита и изоляции одноимённых работ прошли |
| Изменение не ломает соседний код | `go test -timeout 5m ./...`; `go build` для трёх бинарников; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` | Go PASS; все три бинарника собраны; Python compile PASS |
| Полный набор проверен перед слиянием | `python3 -m unittest pilot.test_pilot -v` | 255/257, 13 skipped; 2 падения только в `CorrectionProvenanceStormTests` при restart, вне изменённых функций |

Pinned comparison: base `73f4edce272cb113607540412425d842158e2b81`, candidate `28b68ee16869c55e122e33406341c307b461d83e`.

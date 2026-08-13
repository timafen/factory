# CARD-0128 — Денежный сторож вмешивается после пятого круга

Implementation commit: ddd2cc291eefa04c2ec2e48e58bf254eeb92d33e — ремонты и диагностика изолированы по `work_id`

## HEAD

Status: Implemented.
Branch: `factory/b90560c1-043-0f15c8f1-e4c`.
Implementation commit: ddd2cc291eefa04c2ec2e48e58bf254eeb92d33e — сторож изолирует ремонт, лимит и диагностическую историю по `work_id`.
What changed: `begin_diag_repair()` получает `work_id`, отбирает активные задачи через `same_task_work()` и хранит ремонт отдельно для каждой работы. `recent_stage_text()` и поиск ветки используют ту же изоляцию.
Evidence: `python3 -m unittest pilot.test_pilot.DiagnosisRepairTests -v` — 20/20, `OK`; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` — код 0.
One next action: провести Review поставки относительно свежей основной ветки.

## LOG

### 2026-08-13 — Implement

Исправлено сопоставление ранней диагностики с современными задачами: вместо владельческого заголовка счётчик получает задачу с устойчивым `work_id`.
Добавлены регрессии на срабатывание ровно на пятом круге и изоляцию одноимённых работ; 19 целевых сценариев прошли, синтаксическая компиляция завершилась с кодом 0.

### 2026-08-13 — Implement

После замечаний Review ремонт, лимит диагностики и диагностическая история переведены с заголовка на `work_id`; старые задачи без идентификатора сохраняют прежнее сопоставление по заголовку.
Добавлен немоканный регрессионный путь `diag_sweep()` → `begin_diag_repair()` для двух одновременных одноимённых работ: каждая отменяется и сохраняется отдельно, а чужая история не попадает в разбор.
`python3 -m unittest pilot.test_pilot.DiagnosisRepairTests -v` — 20/20, `OK`; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` — код 0.

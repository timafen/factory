# CARD-0128 — Денежный сторож вмешивается после пятого круга

Implementation commit: 2e64a7006667462948c6682e8f356037fd65b3d9 — денежный сторож и повторные запуски восстанавливают ветку по `work_id`

## HEAD

Status: Implemented and target-tested; awaiting Review.
Branch: `factory/e56fa4be-f90-29d00215-dce`.
Implementation commit: 2e64a7006667462948c6682e8f356037fd65b3d9 — сторож изолирует ремонт, лимит и диагностическую историю по `work_id`, а повторы восстанавливают ветку.
What changed: `diag_sweep()` считает круги современной задачи по устойчивому `work_id`, поэтому сторож срабатывает на пятом круге. Все современные пути поиска ветки передают `work_id`; legacy-история по-прежнему ищется по тексту.
Evidence: `python3 -m unittest pilot.test_pilot.DiagnosisRepairTests pilot.test_pilot.PipelineWatchTests pilot.test_pilot.AnswerEscalationTests -v` — 35/35, `OK`; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` — exit 0.
One next action: perform Review against the published branch.

## LOG

### 2026-08-13 — Implement

Восстановлена чистая реализация на свежем `origin/main`: ранняя диагностика, её лимит, история и авторемонт разделены по `work_id`.
Регрессии подтверждают срабатывание ровно на пятом круге и независимую отмену двух одноимённых работ.
`python3 -m unittest pilot.test_pilot.DiagnosisRepairTests -v` — 20/20, `OK`; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` — exit 0.

### 2026-08-13 — Implement

Исправлена регрессия восстановления ветки: повтор современной работы передаёт `work_id`, а legacy-записи остаются совместимыми с текстовой ссылкой.
Добавлены отдельные проверки modern retry по `work_id` и legacy-текста; конвейер и ответы также проверены вместе со сторожем.
`python3 -m unittest pilot.test_pilot.DiagnosisRepairTests pilot.test_pilot.PipelineWatchTests pilot.test_pilot.AnswerEscalationTests -v` — 35/35, `OK`; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` — exit 0.

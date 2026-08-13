# CARD-0128 — Денежный сторож вмешивается после пятого круга

Implementation commit: d68fb4ec443e651e69568f9b9f2435ce04300ec9 — ремонты и диагностика изолированы по `work_id`

## HEAD

Status: Implemented and target-tested; awaiting Review.
Branch: `factory/5c06cd33-ba0-0ec83885-de8`.
Implementation commit: d68fb4ec443e651e69568f9b9f2435ce04300ec9 — сторож изолирует ремонт, лимит и диагностическую историю по `work_id`.
What changed: `diag_sweep()` считает круги современной задачи по устойчивому `work_id`, поэтому сторож срабатывает на пятом круге. Одноимённые работы ремонтируются и восстанавливаются независимо.
Evidence: `python3 -m unittest pilot.test_pilot.DiagnosisRepairTests -v` — 20/20, `OK`; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` — exit 0.
One next action: perform Review against the published branch.

## LOG

### 2026-08-13 — Implement

Восстановлена чистая реализация на свежем `origin/main`: ранняя диагностика, её лимит, история и авторемонт разделены по `work_id`.
Регрессии подтверждают срабатывание ровно на пятом круге и независимую отмену двух одноимённых работ.
`python3 -m unittest pilot.test_pilot.DiagnosisRepairTests -v` — 20/20, `OK`; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` — exit 0.

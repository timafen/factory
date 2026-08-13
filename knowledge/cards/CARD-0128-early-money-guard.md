# CARD-0128 — Денежный сторож вмешивается после пятого круга

Implementation commit: f0b4f33fe938316a7614bcdf7c916e1051ff5b8f — денежный сторож и повторные запуски разделены по устойчивому `work_id`

## HEAD

Status: Implemented and targeted checks pass.
Branch: `factory/c7d2c646-3cc-4531f9e1-af7`.
Implementation commit: f0b4f33fe938316a7614bcdf7c916e1051ff5b8f — сторож изолирует диагностику, лимит и авторемонт по `work_id`, а повторы восстанавливают ветку.
What changed: `diag_sweep()` считает круги современной задачи по устойчивому `work_id`, поэтому вмешательство начинается на пятом круге. Одноимённые работы не смешиваются; legacy-история по-прежнему ищется по тексту.
Evidence: `python3 -m unittest pilot.test_pilot.DiagnosisRepairTests pilot.test_pilot.PipelineWatchTests pilot.test_pilot.AnswerEscalationTests -v` — 35/35, `OK`; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` — exit 0; `git diff --check origin/main...HEAD` — PASS.
One next action: провести Review закреплённого удалённого снимка ветки.

## LOG

### 2026-08-13 — Implement

Реализация перенесена точечным коммитом на свежий `origin/main`, без отката более новой логики арбитража областей.
Диагностика, лимиты и авторемонт разделены по `work_id`; восстановление ветки сохраняет совместимость с legacy-текстом.
Целевой набор — 35/35, `OK`; `py_compile` и проверка пробелов прошли.

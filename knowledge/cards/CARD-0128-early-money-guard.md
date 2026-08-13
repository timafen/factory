# CARD-0128 — Денежный сторож вмешивается после пятого круга

Implementation commit: 2e64a7006667462948c6682e8f356037fd65b3d9 — денежный сторож и повторные запуски восстанавливают ветку по `work_id`

## HEAD

Status: Verified PASS — awaiting human merge.
Branch: `factory/e56fa4be-f90-29d00215-dce`.
Implementation commit: 2e64a7006667462948c6682e8f356037fd65b3d9 — сторож изолирует ремонт, лимит и диагностическую историю по `work_id`, а повторы восстанавливают ветку.
What changed: `diag_sweep()` считает круги современной задачи по устойчивому `work_id`, поэтому сторож срабатывает на пятом круге. Современные пути восстановления ветки передают `work_id`; legacy-история по-прежнему ищется по тексту.
Evidence: целевой набор `python3 -m unittest pilot.test_pilot.DiagnosisRepairTests pilot.test_pilot.PipelineWatchTests pilot.test_pilot.AnswerEscalationTests -v` — 35/35, `OK`; `py_compile` и pinned `git diff --check` — PASS. Полный набор — 259 тестов, 2 старых падения и 13 skipped; оба падения воспроизводятся на pinned base в неизменённом `CorrectionProvenanceStormTests`.
One next action: merge the verified implementation branch.

## LOG

### 2026-08-13 — Implement

Восстановлена чистая реализация на свежем `origin/main`: ранняя диагностика, её лимит, история и авторемонт разделены по `work_id`.
Регрессии подтверждают срабатывание ровно на пятом круге и независимую отмену двух одноимённых работ.
`python3 -m unittest pilot.test_pilot.DiagnosisRepairTests -v` — 20/20, `OK`; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` — exit 0.

### 2026-08-13 — Implement

Исправлена регрессия восстановления ветки: повтор современной работы передаёт `work_id`, а legacy-записи остаются совместимыми с текстовой ссылкой.
Добавлены отдельные проверки modern retry по `work_id` и legacy-текста; конвейер и ответы также проверены вместе со сторожем.
`python3 -m unittest pilot.test_pilot.DiagnosisRepairTests pilot.test_pilot.PipelineWatchTests pilot.test_pilot.AnswerEscalationTests -v` — 35/35, `OK`; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` — exit 0.

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Денежный сторож вмешивается на пятом круге | `DiagnosisRepairTests` в целевом наборе | PASS: современная работа с `work_id` запускает диагностику ровно на пороге 5. |
| Одноимённые современные работы не смешиваются | `test_live_sweep_does_not_count_same_title_from_another_work`, `test_live_sweep_repairs_same_title_works_separately_by_work_id` | PASS: работы считаются и отменяются раздельно по `work_id`. |
| Повтор восстанавливает ветку современной работы | `test_branch_from_history_restores_modern_retry_by_work_id` | PASS. |
| Legacy-восстановление сохраняет поиск по тексту | `test_branch_from_history_restores_legacy_text_reference` | PASS. |
| Соседние переходы конвейера и ответы не регрессировали | `python3 -m unittest pilot.test_pilot.DiagnosisRepairTests pilot.test_pilot.PipelineWatchTests pilot.test_pilot.AnswerEscalationTests -v` | PASS: 35/35, `OK`. |
| Полный Pilot-набор | `python3 -m unittest pilot.test_pilot -v` | НАХОДКА: 259 тестов, 2 падения, 13 skipped; те же 2 падения воспроизведены на pinned base в неизменённом `CorrectionProvenanceStormTests`. |
| Поставка ограничена задачей | pinned `git diff --name-only base_sha...candidate_sha`, `git diff --check` | PASS: только `pilot/pilot.py`, `pilot/test_pilot.py`, `knowledge/cards/CARD-0128-early-money-guard.md`; пробелы чистые. |
| Живая проверка стенда | `sudo -n /usr/local/bin/fx staging sandbox bootstrap-accounts | seller-policies | listings` | НАХОДКА: контейнер запрещает `sudo` (`no new privileges`), а `seller-policies` и `listings` недоступны; продуктовая TRY-ссылка не получена. |

Implementation commit: 27d16d8f3e52eb6a8e3491850329f6b104733028 — work_id проведён через реальные остановки, delivery и merge receipt

## HEAD

Status: Implemented — Review required
Branch: factory/78b5df3e-541-0f80a035-c06
Implementation commit: 27d16d8f3e52eb6a8e3491850329f6b104733028 — work_id проведён через реальные остановки, delivery и merge receipt
What changed: остановка бюджета, continuation delivery и merge receipt используют work_id текущей задачи; Plan и epic остаются изолированными для одинаковых title.
Evidence: `python3 -m unittest -v pilot.test_pilot` → 307 OK, 13 skipped; 6 проверок SameTitlePlanEpicBudgetIsolationTests → OK.
One next action: повторить независимый Review до перехода к Verify.

## LOG

### 2026-08-14 — Implement

Исправлены три блокирующих производственных пути: hard-stop бюджета, выбранная ветка delivery и запись merge receipt теперь сохраняют и используют work_id. Добавлены сквозные регрессии для двух одноимённых работ: stop одной не возобновляет вторую, а настоящий writer merge-журнала создаёт receipt только для своей работы. `python3 -m unittest -v pilot.test_pilot` завершился: 307 OK, 13 skipped.

### 2026-08-11 — Implement

Перенесена изоляция по `work_id` на свежий `origin/main` с сохранением новой логики Pilot. Все 218 Pilot-тестов прошли; общий `just check` дошёл до независимых Go-тестов и остановился по их пятиминутному timeout вне области изменения.

### 2026-08-12 — Verify

| Критерий | Команда / проверка | Наблюдаемый результат |
| --- | --- | --- |
| Plan с одинаковым заголовком завершает только свою работу | `SameTitlePlanEpicBudgetIsolationTests.test_plan_completion_never_closes_other_same_title_work` | Завершён только `idea-a`; `idea-b` остаётся в работе. |
| Производители Plan и epic сохраняют разные устойчивые ключи | `SameTitlePlanEpicBudgetIsolationTests.test_plan_and_epic_producers_record_both_same_title_roots` | Созданы отдельные записи состояния для обоих одноимённых корней. |
| Epic и merge receipt не пересекаются по title | `SameTitlePlanEpicBudgetIsolationTests.test_epic_completion_and_merge_receipt_ignore_other_work` | Epic A завершён, Epic B остаётся running; receipt B не найден. |
| Бюджет, расход и history branch разделены | `SameTitlePlanEpicBudgetIsolationTests.test_budget_spend_limit_and_history_branch_are_partitioned` | Расходы, branch и downgrade относятся только к своему `work_id`. |
| Регрессия Pilot | `python3 -m unittest -v pilot.test_pilot` | 224 OK, 13 skipped. |
| Сборка и общий контур | `go build ./...`; `just check`; `just test-browser` | Сборка OK. Общий Go-контур упёрся в 5-минутные timeout в неизменённых `internal/controlplane` и `internal/worker`; browser sandbox не может вызвать `sudo` из-за no-new-privileges. |

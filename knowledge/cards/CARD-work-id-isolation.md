Implementation commit: 86b3e4091e438b5a2574cdc3d6712971cd500c47 — lifecycle Plan, hard-stop, артефакты и merge receipt изолированы по work_id

## HEAD

Status: Implemented — rebased on fresh main
Branch: factory/206f50e6-821-d3af1cda-925
Implementation commit: 86b3e4091e438b5a2574cdc3d6712971cd500c47
What changed: Plan lifecycle, hard-stop бюджета, epic и merge receipt используют durable `work_id`; одинаковые заголовки остаются независимыми.
What changed: при конфликте rebase сохранены поля actor/rounds из main и добавлена запись `work_id` в receipt и merge intent.
Evidence: `python3 -m unittest -v pilot.test_pilot.SameTitlePlanEpicBudgetIsolationTests` → 6 OK; `go build ./...` → OK.
One next action: повторить Review на перебазированной ветке.

## LOG

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

### 2026-08-14 — Implement

Исправлены четыре замечания повторного Review: Plan lifecycle и архив разделены по `work_id`, budget hard-stop больше не теряет аргумент durable key, цикл передаёт ID в artifacts и merge intent, а writer merge-journal сохраняет ID для восстановления epic. Добавлены сквозные проверки lifecycle/hard-stop и настоящей записи/чтения merge receipt. `python3 -m unittest -v pilot.test_pilot` — 226 OK, 13 skipped; `go build ./...` — OK.

После перебазирования сохранён migration bridge для legacy Plan: потомок сопоставляется с legacy-карточкой по ID её корневой задачи, а карточки с provenance по-прежнему изолированы exact `work_id`. `python3 -m unittest -v pilot.test_pilot` — 312 OK, 13 skipped; `go build ./...` — OK.

### 2026-08-15 — Implement

Реализация перенесена на свежий `origin/main`. В конфликте merge receipt сохранены актуальные поля actor/rounds и добавлен `work_id`, поэтому восстановление epic не смешивает одноимённые работы. `python3 -m unittest -v pilot.test_pilot.SameTitlePlanEpicBudgetIsolationTests` — 6 OK; `go build ./...` — OK.

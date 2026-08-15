Implementation commit: bea0d4b2833c6727d803576d2b977f4e70901903 — Plan, epic, бюджеты, артефакты и merge receipt изолированы по work_id

## HEAD

Status: Implemented — awaiting Review
Branch: factory/084b8089-ce7-b0f96498-7fe
Implementation commit: bea0d4b2833c6727d803576d2b977f4e70901903
What changed: lifecycle Plan и архив ищут provenance `work_id`, hard-stop и история бюджета используют durable key, а основной цикл передаёт ID через artifacts и merge intent.
What changed: merge-journal сохраняет `work_id`; title остаётся fallback только для legacy без provenance.
Evidence: `python3 -m unittest -v pilot.test_pilot` → 346 OK, 13 skipped; `go build ./...` → OK; `npx tsc -p tsconfig.app.json --noEmit` → OK.
Evidence: `just check` → статические проверки OK, два timing-теста worker упали; их точечный повтор → OK.
One next action: провести Review изоляции по `work_id`.

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

Работа перенесена на свежий `origin/main`; конфликт с новыми полями actor/rounds разрешён с сохранением `work_id` в merge receipt и intent. Pilot — 346 OK, 13 skipped; Go build и обязательный TypeScript-check прошли. Полный `just check` прошёл статические проверки, но два неизменённых timing-теста worker флуктуировали; их точечный повтор прошёл.

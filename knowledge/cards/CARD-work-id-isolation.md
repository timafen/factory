Implementation commit: 243d6502fc4fb27493600340608ac10e090c0521 — Plan, epic, бюджеты и ветки истории изолированы по work_id

## HEAD

Status: Verified PASS — awaiting human merge
Branch: factory/d6262485-d88-f2b729ce-4fa
Implementation commit: 243d6502fc4fb27493600340608ac10e090c0521
What changed: одноимённые работы больше не делят состояние Plan, epic, бюджетов и history branch; fallback по title оставлен только для legacy-записей без provenance.
Evidence summary: `python3 -m unittest -v pilot.test_pilot` → 224 OK, 13 skipped; четыре целевые проверки изоляции → OK; `go build ./...` → OK. `just check` остановился на таймаутах неизменённых `internal/controlplane` и `internal/worker`; browser-контур недоступен из-за запрета `sudo` в sandbox.
One next action: подтвердить human merge с учётом двух независимых ограничений CI-окружения.

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

Implementation commit: faeee9415b4f6f1b568ce43bb312f88a80d8424d — лимит попыток этапа закреплён за снимком очереди в начале цикла.

# CARD-0164: снимок задач для `stage_attempts()`

## HEAD

Status: Implemented
Branch: factory/a4838cca-5e3-439a24ce-63f
Implementation commit: faeee9415b4f6f1b568ce43bb312f88a80d8424d
What changed: `cycle()` сохраняет неизменяемый снимок для расчёта попыток;
диагностика, ответы владельца и возвраты этапа используют его.
What changed: добавлен регрессионный тест: новая задача видна только следующему снимку.
Evidence: `python3 -m unittest pilot.test_pilot.SameTitlePlanEpicBudgetIsolationTests` → 1 passed.
One next action: передать ветку на Review.

## LOG

### 2026-08-14 — Specification

Проверен актуальный `pilot/pilot.py`: `stage_attempts()` считает совпадения
стадии через `same_task_work`, а решения о лимите вызываются из одного прохода
`cycle()`. Следующая реализация должна сделать границу переданного списка
явной и доказать её тестом: добавленная после снимка задача видна только
следующему проходу. Product code и UI на этапе Specification не изменялись.

### 2026-08-14 — Implement

`cycle()` формирует неизменяемый снимок очереди для лимитов попыток и передаёт
его во все решения текущего прохода. Регрессия доказывает, что добавленная
позже задача учитывается только новым снимком, сохраняя изоляцию по `work_id`.
Проверка: `python3 -m unittest pilot.test_pilot` — 290 passed, 13 skipped.

### 2026-08-14 — Implement

После rebase на актуальный `main` конфликт разрешён в пользу неизменяемого
`attempt_tasks`: диагностика, ответы и возвраты не подхватывают задачи,
созданные в том же цикле. Проверка:
`python3 -m unittest pilot.test_pilot.SameTitlePlanEpicBudgetIsolationTests` — 1 passed.

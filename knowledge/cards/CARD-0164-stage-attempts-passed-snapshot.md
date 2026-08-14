Implementation commit: eda8eb36bba83c20cdf3ab860d4421f395c81b2e — лимит попыток этапа закреплён за снимком очереди в начале цикла.

# CARD-0164: снимок задач для `stage_attempts()`

## HEAD

Status: Implemented
Branch: factory/e65886f2-f99-690322ef-55f
Implementation commit: eda8eb36bba83c20cdf3ab860d4421f395c81b2e
What changed: `cycle()` сохраняет неизменяемый снимок для расчёта попыток;
диагностика, ответы владельца и возвраты этапа используют его.
What changed: добавлен регрессионный тест: новая задача видна только следующему снимку.
Evidence: `python3 -m unittest pilot.test_pilot` → 290 passed, 13 skipped.
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

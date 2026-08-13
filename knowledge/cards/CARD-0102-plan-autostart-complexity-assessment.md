# CARD-0102 — Карточки Плана получают оценку сложности при автозапуске

Implementation commit: e43462307fcd7c25003eecfe693fd21a9dfe8ba7 — существующий автозапуск Плана служит базовой реализацией; оценка сложности ещё не реализована и определена этой спецификацией.

## HEAD

- Status: Specification complete — ожидает Implement + Test.
- Branch: `factory/1e90aded-177-04960ada-3fa`.
- Specification: `knowledge/specs/plan-autostart-complexity-assessment.md`.
- Owner impact: автозапуск будет выбирать исполнителя по оценённой сложности и
  показывать владельцу саму оценку с понятным основанием.
- Scope: `pilot/pilot.py`, `pilot/test_pilot.py`, `intake/plan.py`.
- Evidence target: `python3 -m unittest pilot.test_pilot.PlanAutostartTest`.
- Next action: реализовать сохранение, маршрутизацию, отказоустойчивость и
  отображение оценки по спецификации.

## LOG

### 2026-08-12 — Specification

Фактический код подтвердил, что автозапуск всегда передаёт в `stage_worker`
константу `medium`, а карточка не хранит сложность. Определена единая граница:
до создания задачи получить строгую оценку `low|medium|high`, сохранить её с
русским основанием, использовать для первого worker и повторно не оценивать.
Невалидная оценка не маскируется как `medium` и не переводит карточку в работу.

Предыдущая Triage-ветка `factory/b6ffc762-239-c969ae3d-2ea` отсутствовала в
origin на момент Specification; документ опирается на свежий `origin/main` и
фактические тестовые границы `PlanAutostartTest`.

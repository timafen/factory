# CARD-0073 — Изоляция снимка задач Пилота

Implementation commit: pending — спецификация текущего этапа; реализация будет
зафиксирована отдельным коммитом следующего этапа.

## Scope

Функции в `pilot/pilot.py` должны принимать решения только по переданному
снимку `tasks`. Карточка относится к регрессии подсчёта stage attempts и
приоритета terminal handoff между независимыми work/repository.

## Handoff

Спецификация: `knowledge/specs/pilot-task-snapshot-isolation.md`.
Реализация должна изменить только `pilot/pilot.py` и `pilot/test_pilot.py`,
добавив целевой класс `TaskSnapshotIsolationTests` и сохранив API и UI.


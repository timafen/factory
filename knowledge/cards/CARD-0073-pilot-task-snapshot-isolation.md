# CARD-0073 — Изоляция снимка задач Пилота

Implementation commit: 17564d397ff9ab2e6954393969444f3f21d916cd — зафиксирована
спецификация; реализация будет отдельным коммитом следующего этапа.

## Scope

Функции в `pilot/pilot.py` уже принимают решения только по переданному снимку
`tasks`: глобальных чтений и добавления чужих завершений в них нет, а call
sites передают снимок текущего цикла. Карточка относится к регрессионной защите
подсчёта stage attempts и приоритета terminal handoff между независимыми
work/repository.

## Handoff

Спецификация: `knowledge/specs/pilot-task-snapshot-isolation.md`.
Реализация должна изменить только `pilot/test_pilot.py`, добавив целевой класс
`TaskSnapshotIsolationTests`; продуктовый код, API и UI менять не требуется.

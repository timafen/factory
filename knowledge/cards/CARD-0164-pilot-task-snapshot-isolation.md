# CARD-0164 — Изоляция снимка задач Пилота

Implementation commit: d7701d23b6c354555cf4536e33492632fd81473c — добавлены регрессионные тесты изоляции снимка задач

## HEAD

- Status: Implemented and tested
- Branch: `factory/0c177ad0-8b2-24096ada-66f`
- Implementation commit: `d7701d23b6c354555cf4536e33492632fd81473c`
- What changed: тесты фиксируют, что подсчёт попыток и приоритет terminal handoff используют только переданный snapshot и не изменяют входные списки.
- Evidence: `python3 -m unittest -v pilot.test_pilot.TaskSnapshotIsolationTests` → 2 tests, OK.
- One next action: выполнить Review поставки относительно свежего `origin/main`.

## LOG

### 2026-08-14 — Implement

Добавлен `TaskSnapshotIsolationTests`: покрыты два независимых snapshot, пустой
snapshot, чужая terminal-задача, recovery id и неизменность исходных списков.
Целевая команда завершилась успешно: 2 tests, OK.

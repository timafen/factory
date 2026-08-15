Implementation commit: 2fd8ff6b9d06d3a85a611ab61ebe0ce4ce910402 — повторный AUTO-MERGE-конфликт создаёт новое исправление для обновлённой ветки

# Повторное исправление AUTO-MERGE-конфликта

## HEAD

- Status: Implemented and verified
- Branch: `factory/c454ea9b-485-9dd39649-5ce`
- Implementation commit: `2fd8ff6b9d06d3a85a611ab61ebe0ce4ce910402`
- What changed: Pilot запоминает SHA, для которого создан `merge_conflict_return`. Новый конфликт на другом SHA создаёт новую задачу исправления, а повторный цикл на том же SHA остаётся идемпотентным.
- Evidence: `python3 -m unittest pilot.test_pilot.MergeConflictRecoveryTests` → 9 passed; `python3 -m unittest pilot.test_pilot` → 341 passed, 13 skipped.
- One next action: влить ветку в `main`.

## LOG

### 2026-08-15 — Implement

Добавлено различение последовательных конфликтов по SHA вершины ветки и регрессионный сценарий повторного конфликта. Целевые 9 тестов и полный модуль из 341 теста прошли; 13 тестов штатно пропущены.

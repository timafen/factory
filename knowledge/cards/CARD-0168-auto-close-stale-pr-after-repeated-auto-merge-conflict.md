# CARD-0168 — закрывать устаревший PR после повторного AUTO-MERGE-конфликта

Implementation commit: 964fa6df8dc57af1fa13391a7edf99a5a98bc04a — Pilot закрывает только подтверждённый устаревший PR после второго конфликта.

## HEAD

Status: Implemented — ожидает Review.
Branch: `factory/e1fdfd07-359-c2a5775b-221`.
Implementation commit: 964fa6df8dc57af1fa13391a7edf99a5a98bc04a — exact work marker, безопасное закрытие stale PR и регрессия.
What changed: новый PR Pilot получает marker immutable `work_id`; при втором
conflict проверяется единственный открытый PR и единственный merged PR с тем же
marker и base, после чего закрывается только текущий stale PR.
Evidence: `python3 -m unittest -q pilot.test_pilot.MergeConflictRecoveryTests` → 9 tests, OK.
One next action: выполнить независимый review fail-closed условий GitHub lookup и close.

## LOG

### 2026-08-15 — Implement

В `merge_intent` сохранены `work_id`, target base и число конфликтов. После
второго AUTO-MERGE-конфликта Pilot закрывает текущий PR только при точном
machine marker у уже merged PR; неясные ответы сохраняют обычный repair flow.
Целевая регрессия подтверждает один close, terminal `superseded` и отсутствие
повторного действия при restart; весь `MergeConflictRecoveryTests` зелёный.

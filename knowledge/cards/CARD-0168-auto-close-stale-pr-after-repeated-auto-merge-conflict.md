# CARD-0168 — закрывать устаревший PR после повторного AUTO-MERGE-конфликта

Implementation commit: 7654b331ccb4fa88d79557719f8d96d306d08b11 — Pilot закрывает устаревший PR после доказанного слияния той же работы и возвращает её в correction flow при ошибке.

## HEAD

Status: Implemented — спецификация приёмки подготовлена.
Branch: реализация влита в `main`; текущая спецификация передаёт её на приёмку.
Implementation commit: 7654b331ccb4fa88d79557719f8d96d306d08b11 — отказ `gh_close_pr` сохраняет восстановимый conflict.
What changed: новый PR Pilot получает marker immutable `work_id`; при втором
conflict проверяется единственный открытый PR и единственный merged PR с тем же
marker и base. Состояние становится terminal только после успешного закрытия;
ошибка GitHub оставляет conflict для обычной correction-задачи.
Evidence: `python3 -m unittest -q pilot.test_pilot.MergeConflictRecoveryTests` → 10 tests, OK; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` → OK.
One next action: повторить независимый Review переходов close failure и recovery.

## LOG

### 2026-08-15 — Implement

В `merge_intent` сохранены `work_id`, target base и число конфликтов. После
второго AUTO-MERGE-конфликта Pilot закрывает текущий PR только при точном
machine marker у уже merged PR; неясные ответы сохраняют обычный repair flow.
Целевая регрессия подтверждает один close, terminal `superseded` и отсутствие
повторного действия при restart; весь `MergeConflictRecoveryTests` зелёный.

### 2026-08-15 — Implement

После замечания Review запись terminal-состояния перенесена за успешный
`gh_close_pr`: при отказе GitHub intent остаётся `conflict`, а следующий шаг
создаёт correction-задачу. Регрессия отказа и весь класс из 10 тестов зелёные;
оба Python-файла успешно прошли `py_compile`.

# CARD-0127 — Статус `Implemented` в HEAD карточки

Implementation commit: 9929283bf18f09b1b67adf4a2b1b1ac3ba82b25d — базовая реализация свежего snapshot-gate, на который опирается проверка статуса карточки

- Status: Specification — ожидает реализацию проверки статуса.
- Scope: `pilot/pilot.py`, `pilot/test_pilot.py` и связанная спецификация.
- Goal: Review принимает карточку только при явно зафиксированном `Status: Implemented` в опубликованном HEAD.
- Acceptance: положительный сценарий и защитные тесты для старого, отсутствующего и чужого статуса; ошибки remote не маскируются под дефект карточки.
- Next action: реализовать ворота и целевой набор тестов по `knowledge/specs/card-head-implemented-status.md`.

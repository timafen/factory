# CARD-0093 — Mock-объекты не попадают в production dashboard

Implementation commit: отсутствует — этап Specification, продуктовый код намеренно не изменялся.

## HEAD

- Status: Specification ready.
- Branch: `factory/f7052427-ed2-18384336-a1d`.
- Specification: `knowledge/specs/production-dashboard-mock-leak.md`.
- Owner outcome: dashboard сохраняет последний корректный снимок и не показывает
  внутренние представления тестовых Mock-объектов.
- Implementation scope: `pilot/pilot.py`, `pilot/test_pilot.py`.
- Required check: `python3 -m unittest -v pilot.test_pilot.DashboardSnapshotIsolationTests`.
- Next action: реализовать изоляцию пути и проверку снимка на стадии Implement + Test.

## LOG

### 2026-08-12 — Specification

Фактический поток данных прослежен от `pilot.write_dashboard` и общего
`DASH_PATH` через JSON-файл к пассивному Go handler и React Overview. Выбрана
защита в месте публикации: тестовые записи направляются во временный файл, а
невалидный снимок не заменяет последний хороший. UI и API-маршрут не входят в
область изменения.

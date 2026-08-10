# CARD-0056 — Четыре полезные работы из Плана

Implementation commit: 4b9c5d2c5e14a9c57337d7562bb1fc6cfb2dc3cc — Pilot получил лимит четырёх независимых работ и выбор свободного настроенного воркера.

## HEAD

- Status: Specification ready for alignment.
- Specification: `knowledge/specs/plan-priority-autostart.md`.
- Current truth: `origin/main` уже содержит основное поведение; следующая стадия
  сверяет его с критериями и добавляет единый целевой регрессионный тест.
- Scope: `pilot/pilot.py`, `pilot/test_pilot.py`.
- Required check: `python3 -m unittest pilot.test_pilot.PlanAutostartTest.test_four_work_limit_and_free_worker_distribution`.

## LOG

### 2026-08-10 — Specification

Спецификация актуализирована с трёх до четырёх независимых работ и связывает
автоподбор со свободной ёмкостью настроенных воркеров. Зафиксированы границы,
критерии приёмки и проверяемые обещания для следующей стадии.

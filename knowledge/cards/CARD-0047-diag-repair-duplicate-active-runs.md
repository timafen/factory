# CARD-0047 — Автопочинка не считает один запуск дважды

## HEAD

- Status: Specification готова к реализации.
- Branch: `factory/0e02a4e5-03d-d0e5d336-e95`.
- Specification: `knowledge/specs/diag-repair-duplicate-active-runs.md`.
- Goal: не останавливать безопасную автопочинку из-за повтора одного ID на
  границе страниц списка задач, сохранив запрет на отмену двух разных запусков.
- Implementation scope: `pilot/pilot.py`, `pilot/test_pilot.py`.
- Required check: `python3 -m unittest pilot.test_pilot.DiagnosisRepairTests`.
- One next action: реализовать дедупликацию по ID и регрессионный тест.

## LOG

### 2026-08-10 — Specification

Зафиксирован минимальный контракт исправления ложной неоднозначности: повтор одного
активного ID в курсорной выдаче считается одним запуском, а разные ID и записи без
ID сохраняют безопасный отказ от автоматической отмены.

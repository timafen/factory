# CARD-0103 — Разово закрыть старые зависшие карточки Плана

Implementation commit: 596e7a7a0b6d687a7ceb99d9d06ea803b574721b — реализована безопасная разовая уборка старых карточек Плана.

## HEAD

- Status: Implemented and target tests green.
- Branch: `factory/0ec8247d-42a-1c1f3c03-aa0`.
- Implementation commit: `596e7a7a0b6d687a7ceb99d9d06ea803b574721b`.
- What changed: добавлена операторская команда с dry-run по умолчанию и
  атомарным `--apply`; записи не удаляются и сохраняют связь с задачей.
- Evidence: `python3 -m unittest pilot.test_pilot.LegacyPlanCardCleanupTest
  pilot.test_pilot.PlanCardCleanupTest` — 11 tests, OK.
- One next action: проверить dry-run с фактической датой внедрения перед применением.

## LOG

### 2026-08-12 — Implement

Реализована разовая консервативная уборка завершённых до границы и потерявших
задачу карточек. Защитные сценарии оставляют активные, отменённые, новые и
неоднозначные работы без изменений; повторное применение не переписывает файл.
Целевой и регрессионный классы: 11 tests, OK; `py_compile` и `git diff --check`
завершились с кодом 0.

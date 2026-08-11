# CARD-0075 — Лимит возврата расходуется после запуска повторной задачи

## HEAD

- Status: Specification — awaiting implementation.
- Branch: `factory/e4d2fdb7-bbb-231efe4e-07d`.
- Specification: `knowledge/specs/rescue-return-after-task-create.md`.
- What changes: rescue/return cap фиксируется только после успешного
  `create_task`; ошибка создания оставляет право на повторный цикл.
- Scope: `pilot/pilot.py`, `pilot/test_pilot.py`; UI, API, схемы данных,
  общие лимиты и circuit breaker не меняются.
- Related: `CARD-0069` — предыдущая спецификация handoff; CARD-0070–0074 не
  используются для этого workstream.

## LOG

### 2026-08-11 — Specification

Зафиксирован порядок: сначала фактический запуск повторной задачи, затем
счётчик rescue, уведомление и история. План охватывает прямые возвраты
`SPEC_BRANCH`, `SPEC`, `INFRA`, `MERGE`, отложенные `GATE`/`DIRT`, а также
регрессию рестарта и повторного цикла после ошибки создания.

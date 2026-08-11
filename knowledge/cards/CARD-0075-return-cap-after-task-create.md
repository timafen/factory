# CARD-0075 — Лимит возврата расходуется после запуска повторной задачи

## HEAD

- Status: Implemented — awaiting Verify.
- Branch: `factory/aa3c4c2a-d79-ec3d31d8-811`.
- Implementation commit: 76742d924f06eec1fd10c36173fe90a10869f62c —
  возврат фиксируется только после создания повторной задачи.
- Specification: `knowledge/specs/rescue-return-after-task-create.md`.
- What changed: `SPEC_BRANCH`, `SPEC`, `GATE`, `DIRT`, `INFRA` и `MERGE`
  используют единый post-create учёт; ошибка освобождает `processed` для повтора.
- Evidence: `SpecificationBranchHandoffTests` — 15/15 OK; `py_compile` — OK;
  `git diff --check` — OK.
- Next action: Verify запускает полный `python3 -m unittest -v pilot.test_pilot`.
- Related: `CARD-0069` — предыдущая спецификация handoff; CARD-0070–0074 не
  используются для этого workstream.

## LOG

### 2026-08-11 — Specification

Зафиксирован порядок: сначала фактический запуск повторной задачи, затем
счётчик rescue, уведомление и история. План охватывает прямые возвраты
`SPEC_BRANCH`, `SPEC`, `INFRA`, `MERGE`, отложенные `GATE`/`DIRT`, а также
регрессию рестарта и повторного цикла после ошибки создания.

### 2026-08-11 — Implement

Добавлен единый post-create примитив для возвратных задач и отложенные маркеры
`GATE`/`DIRT`. Ошибки `create_task`, включая `no_eligible_worker`, не меняют
durable cap, не уведомляют о возврате и освобождают исходную задачу для нового
цикла или рестарта. Целевые 15 тестов, `py_compile` и `git diff --check` прошли.

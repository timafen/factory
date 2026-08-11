# CARD-0075 — Лимит возврата расходуется после запуска повторной задачи

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/aa3c4c2a-d79-ec3d31d8-811`.
- Implementation commit: 5d873f05bac8e1276b8f648188693698e9092c6e —
  возврат фиксируется только после создания повторной задачи.
- Specification: `knowledge/specs/rescue-return-after-task-create.md`.
- What changed: `SPEC_BRANCH`, `SPEC`, `GATE`, `DIRT`, `INFRA` и `MERGE`
  используют единый post-create учёт; ошибка освобождает `processed` для повтора.
- Evidence: `python3 -m unittest -v pilot.test_pilot` — 183/183 OK;
  `go test -timeout 5m ./...`, UI lint/typecheck/tests и tooling/launcher — OK.
- Next action: человек проверяет и вливает ветку.
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

### 2026-08-11 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Лимит расходуется только после ID новой задачи для `SPEC_BRANCH`, `SPEC`, `GATE`, `DIRT`, `INFRA`, `MERGE` | `test_cap_rescue_primitive_records_each_return_only_after_task_id` | Исключение и ответ без ID сохраняют счётчик 0; ID увеличивает его до 1 для всех шести этапов. |
| Неудачный возврат можно повторить в следующем цикле и после рестарта | `test_next_cycle_retries_failed_spec_return_and_records_one_success`, `test_restart_retries_failed_branch_return_with_same_durable_cap` | Один успешный возврат, одно уведомление и корректный durable cap. |
| Ошибка создания не оставляет задачу обработанной и не уведомляет владельца | `test_failed_spec_branch_return_keeps_cap_notification_and_processed_clear` | `processed` очищен, cap не записан, уведомления нет. |
| Полные ветви cycle для `INFRA` и `MERGE` не регрессировали | `python3 -m unittest -v pilot.test_pilot` | 183 теста прошли за 30,467 с. |

Общий набор прошёл: `go test -timeout 5m ./...`, `npm run lint`, `npm run typecheck`,
`npm test`, tooling и launcher. `git diff --check` не нашёл ошибок пробелов.

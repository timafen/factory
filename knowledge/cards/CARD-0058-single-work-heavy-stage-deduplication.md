# CARD-0058 — Одна работа не запускает тяжёлую проверку дважды

Implementation commit: 6fc0c023d044017381928f5193bca6f140def00d — устранён запуск параллельных Verify одной работы из одного снимка.

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/0cdc3d90-86b-828cd3bf-1f4`.
- Implementation commit: 6fc0c023d044017381928f5193bca6f140def00d — новая задача следующей стадии попадает в снимок текущего цикла.
- What changed: после успешного handoff `cycle()` добавляет ответ сервера в `tasks`; `created` считается живой задачей для существующей защиты `live_or_done_at()`.
- What changed: регрессия подтверждает один Verify для двух успешных Implement одной работы; соседний тест сохраняет четыре параллельные разные работы.
- Evidence: полный `python3 -m unittest pilot.test_pilot` → 103 tests OK; целевые сценарии дедупликации и независимого параллелизма → 2 tests OK; `go test -timeout 5m ./...` и статические проверки прошли.
- One next action: проверить и влить изменения человеком.

## LOG

### 2026-08-10 — Implement

В одном цикле ответ успешного создания следующей стадии теперь сразу участвует в дедупликации, поэтому второй терминальный дубль не занимает отдельного воркера Verify. Целевая регрессия и сценарий четырёх независимых handoff прошли: 2 tests OK.

### 2026-08-10 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Одна работа не создаёт параллельный тяжёлый Verify | `test_duplicate_terminal_attempts_start_one_heavy_next_stage` | Второй завершённый Implement видит созданный Verify со статусом `created` и пропускается; 1 задача. |
| Независимые работы сохраняют параллелизм | `test_four_parallel_handoffs_create_each_next_stage_once` | Четыре разные работы создали по одной следующей стадии; 4 задачи. |
| Регрессии Python-оркестратора | `python3 -m unittest pilot.test_pilot` | 103 tests OK. |
| Регрессии Go-контролплейна | `go test -timeout 5m ./...` | Все пакеты прошли. |

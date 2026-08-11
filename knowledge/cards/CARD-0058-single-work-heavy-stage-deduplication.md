# CARD-0058 — Одна работа не запускает тяжёлую проверку дважды

Implementation commit: 6fc0c023d044017381928f5193bca6f140def00d — устранён запуск параллельных Verify одной работы из одного снимка.

## HEAD

- Status: Implemented and tested.
- Branch: `factory/0cdc3d90-86b-828cd3bf-1f4`.
- Implementation commit: 6fc0c023d044017381928f5193bca6f140def00d — новая задача следующей стадии попадает в снимок текущего цикла.
- What changed: после успешного handoff `cycle()` добавляет ответ сервера в `tasks`; `created` считается живой задачей для существующей защиты `live_or_done_at()`.
- What changed: регрессия подтверждает один Verify для двух успешных Implement одной работы; соседний тест сохраняет четыре параллельные разные работы.
- Evidence: `python3 -m unittest pilot.test_pilot.AdaptivePollingTests.test_duplicate_terminal_attempts_start_one_heavy_next_stage pilot.test_pilot.AdaptivePollingTests.test_four_parallel_handoffs_create_each_next_stage_once` → 2 tests OK.
- One next action: выполнить полный набор `python3 -m unittest pilot.test_pilot` на стадии Verify.

## LOG

### 2026-08-10 — Implement

В одном цикле ответ успешного создания следующей стадии теперь сразу участвует в дедупликации, поэтому второй терминальный дубль не занимает отдельного воркера Verify. Целевая регрессия и сценарий четырёх независимых handoff прошли: 2 tests OK.

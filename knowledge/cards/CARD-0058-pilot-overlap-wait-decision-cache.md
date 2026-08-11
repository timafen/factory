Implementation commit: 313701a273783fc0b3d95f689b3bbfd9c78969c4 — Пилот сохраняет решение завершённого этапа на время ожидания пересекающейся работы

# CARD-0058 — Ожидание пересечения без повторного решения модели

## HEAD

Status: Implement + Test — готово

Branch: `factory/f7613675-151-df84f44b-98a`

Implementation commit: 313701a273783fc0b3d95f689b3bbfd9c78969c4 — решение этапа сохраняется по `task_id`, переживает сохранение состояния и повторно используется после снятия пересечения.

What changed: `cycle()` один раз получает решение модели для terminal-задачи и сохраняет весь ответ. `run_loop()` безопасно загружает кэш и оставляет не более 2000 последних решений.

Evidence: `python3 -m unittest -v pilot.test_pilot.AdaptivePollingTests.test_overlap_wait_reuses_decision_across_poll_cycles` → OK; `python3 -m unittest pilot.test_pilot` → 161 tests, OK; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` → exit 0.

One next action: провести Review реализации и регрессионного сценария.

## LOG

### 2026-08-10 — Implement

- Два последовательных ожидания ворот Review не вызвали повторный `decide()` и не создали задачу; после JSON round-trip состояния и освобождения области следующий этап создан один раз.
- Старое состояние без кэша и повреждённое значение восстанавливаются в пустой словарь; 2001 запись обрезается до последних 2000.
- Полный набор `pilot.test_pilot`: 161 тест, OK. Синтаксическая проверка обоих изменённых Python-файлов: exit 0.

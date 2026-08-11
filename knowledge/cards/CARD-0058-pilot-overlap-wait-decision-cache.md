# CARD-0058 — Ожидание пересечения не перезапускает модель

Implementation commit: a718ac619ee2d5a6c5a9d73f6799e3dcbf14f3ad — решение завершённой стадии сохраняется до освобождения пересекающейся области.

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/50588b62-b68-fa55f03b-ba1`.
- Implementation commit: a718ac619ee2d5a6c5a9d73f6799e3dcbf14f3ad — решение модели переиспользуется во время `AREA WAIT` и удаляется после продолжения работы.
- What changed: циклы ожидания общего замка области и ворот Review больше не вызывают `decide()` каждые 30 секунд.
- What changed: после снятия пересечения сохранённое решение запускает следующую стадию без дополнительного обращения к модели.
- Evidence: `just build` → PASS; `just test` → PASS; полный `python3 -m unittest pilot.test_pilot` → 162 tests OK, включая оба сценария ожидания.
- One next action: выполнить human merge ветки в `main`.

## LOG

### 2026-08-10 — Implement

Добавлено сохраняемое состояние решения для работ, остановленных пересечением области. Два регрессионных сценария воспроизводят ожидание в течение двух циклов, освобождают общий замок или ворота Review и подтверждают один вызов модели и один запуск следующей стадии.

### 2026-08-10 — Implement

Карточка восстановлена по ожидаемому машинной проверкой пути `CARD-0058-pilot-overlap-wait-decision-cache.md`. Целевые сценарии повторно прошли: 2 tests OK.

### 2026-08-10 — Implement

Работа пересобрана от свежего `origin/main` без посторонних файлов. Обязательный сценарий получил имя `test_overlap_wait_reuses_decision_across_poll_cycles`; точечная приёмка прошла (1 test OK), оба сценария ожидания прошли (2 tests OK), `py_compile` и `just build` завершились успешно.

### 2026-08-10 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| AREA WAIT не вызывает модель каждые 30 секунд | `python3 -m unittest pilot.test_pilot` | 162 tests OK; сценарий `test_overlap_wait_reuses_decision_across_poll_cycles` подтверждает один вызов `decide()` за три цикла и один запуск следующей стадии. |
| Ожидание ворот Review также переиспользует решение | `python3 -m unittest pilot.test_pilot` | 162 tests OK; `test_review_gate_wait_reuses_decision_until_overlap_clears` подтверждает один вызов `decide()` до снятия ворот. |
| Сборка и полный Go-набор не регрессируют | `just build && just test` | PASS: бинарники собраны, все пакеты `go test ./...` завершились успешно. |

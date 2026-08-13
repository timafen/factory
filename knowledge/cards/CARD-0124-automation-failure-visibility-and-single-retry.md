# CARD-0124 — Провалившийся запуск Automation повторяется один раз

Implementation commit: 0e9a0f0b5a2a9fdcd3ee5a8735f2eec72ec7770c — Automation повторяет failed schedule-запуск ровно один раз, включая потерянную lease.

## HEAD

- Статус: Implemented; готово к повторному Review.
- Ветка: `factory/b728b463-117-4dfeacca-149`.
- Implementation commit: `0e9a0f0b5a2a9fdcd3ee5a8735f2eec72ec7770c` —
  Automation повторяет failed schedule-запуск ровно один раз, включая
  потерянную lease.
- Что изменилось: `CompleteAttempt` и `SweepExpired` атомарно возвращают тот же
  execution в единственную retry-очередь; guard-сценарии и нецелевые задачи не
  создают повтор. Экран показывает queued/running/final/skipped состояние.
- Evidence: lifecycle/guard Go-тесты → PASS; `go test ./...` → PASS; UI `68/68`,
  lint, production web build и `go build ./...` → PASS.
- Следующее действие: повторно отправить CARD-0124 на Review.

## LOG

### 2026-08-13 — Specification

Фактический код связывает schedule-occurrence с единственным task/execution, но
после `dispatched` его результат не наблюдает. Оба пути failure — обычный
`CompleteAttempt` и потеря lease в `SweepExpired` — уже сходятся на состоянии
execution `failed`. Определён единый транзакционный compare-and-set: только
первый failure целевого schedule-occurrence возвращает тот же execution в
`queued` и увеличивает `retry_count` до 1. Durable diagnostic и расширенная
Automation projection различают идущий retry, final failure, disablement и
недоступность worker; повтор completion/sweep и перезапуск сервера идемпотентны.

### 2026-08-13 — Implement

Коммит `b413dd0c3ffa15fdde2c088a30a9204e1d567a2d` завершил продуктовую поставку:
Automation повторяет первый failed execution один раз, а встроенный интерфейс
выводит понятные состояния повтора и окончательного сбоя. Целевой Go-тест и пять
UI-сценариев прошли; полный Go/web-набор, lint и production build также зелёные.

### 2026-08-13 — Implement

На чистой ветке от свежего `main` перенесены только файлы CARD-0124; посторонняя
CARD-0125 исключена. Коммит реализации `5748422d2be52600fec3caa78180e81670555204`:
целевой Go-тест, 68 UI-тестов, проверка типов, lint и production build прошли.

### 2026-08-13 — Implement

На чистой ветке добавлены lifecycle/table-проверки scheduled occurrence и
`SweepExpired`: повторные completion/sweep, переоткрытие БД, cancellation,
disablement, offline/unhealthy worker и исключение GitHub/обычных задач
сохраняют identity и число durable-записей exactly-once. Тесты выявили и
закрыли раннее поглощение expired lease очисткой capacity и ошибочный retry
diagnostic для GitHub Automation. Implementation commit:
`0e9a0f0b5a2a9fdcd3ee5a8735f2eec72ec7770c`; полный Go-набор, Go/web build,
68 UI-тестов и lint прошли.

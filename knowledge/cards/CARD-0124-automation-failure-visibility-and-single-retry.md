# CARD-0124 — Провалившийся запуск Automation повторяется один раз

Implementation commit: b413dd0c3ffa15fdde2c088a30a9204e1d567a2d — встроенный интерфейс Automation показывает автоматический повтор и окончательный сбой запуска.

## HEAD

- Статус: Implemented.
- Ветка: `factory/d1ee5c50-b00-7430415d-021`.
- Implementation commit: `b413dd0c3ffa15fdde2c088a30a9204e1d567a2d` —
  встроенный интерфейс Automation показывает автоматический повтор и
  окончательный сбой запуска.
- Что изменилось: первый failure scheduled или Run now запуска атомарно ставит
  тот же execution в единственную повторную очередь; API и экран показывают ход
  повтора, окончательный сбой и причины, по которым повтор невозможен.
- Evidence: `go test ./...` → PASS; web 178/178 → PASS; lint и build → PASS.
- Следующее действие: открыть Automation на стенде и визуально подтвердить
  состояния реального повторного запуска.

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

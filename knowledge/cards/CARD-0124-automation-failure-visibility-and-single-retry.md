# CARD-0124 — Провалившийся запуск Automation повторяется один раз

Implementation commit: ожидается на этапе Implement — Specification не меняет продуктовый код.

## HEAD

- Статус: Specified — ожидает Implement.
- Ветка Specification: `factory/209b85f2-ed1-e28318b7-16e`.
- Спецификация:
  `knowledge/specs/automation-failure-visibility-and-single-retry.md`.
- Влияние на владельца: scheduled и Run now запуск после первого failure один
  раз автоматически повторяется; ход повтора и окончательный провал видны на
  существующем экране Automation.
- Граница: тот же execution/task/occurrence/request key и закреплённый worker;
  cancellation, disablement, недоступный worker, второй failure и server restart
  не создают следующий replay.
- Зависимость: интегрировать owner-facing состояния с CARD-0123, не дублируя её
  экран и модель истории запусков.
- Следующее действие: Implement реализует атомарный retry и указанные Go/UI-
  тесты, после чего заменяет верхнюю строку полным SHA кодового коммита.

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

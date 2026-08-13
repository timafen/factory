# CARD-0124 — Провалившийся запуск Automation повторяется один раз

Implementation commit: ff28d0a639dcbcfef5bc00671c9cb438a0d293ac — Automation автоматически повторяет сбой у исходного исполнителя и точно показывает статус повтора.

## HEAD

- Статус: Verified PASS — ожидает решения человека о слиянии.
- Ветка: `factory/a63ff03a-2de-c125f372-48c`.
- Implementation commit: `ff28d0a639dcbcfef5bc00671c9cb438a0d293ac` —
  автоматический retry привязан к исходному worker и не смешивается с ручным.
- Evidence: 6 целевых Go-сценариев и 5 UI-состояний повтора прошли; все 68
  UI-тестов, сборка трёх Go-бинарников, boundary, launcher, tooling и
  воспроизводимость `web/dist` прошли.
  Общий набор остановлен двумя известными проверками вне области CARD-0124:
  staticcheck `SA4000` и worker integration lost-response.
- Следующее действие: человеку проверить отчёт Verify и принять решение о
  слиянии ветки.

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

Исправлены два блокирующих дефекта Review: повтор больше не может быть забран
другим совместимым worker, а ручной GitHub retry не получает статус
автоматического; отменённый автоматический retry остаётся `cancelled`.
Проверены две совместимые worker, ручной GitHub retry и cancellation;
`go test ./...` и `npm run typecheck` прошли. Implementation commit:
`aad8346add8f23ab1c48a64a7c79050da961637f`.

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

### 2026-08-13 — Verify

Сравнение закреплено между базой
`99701704b37e8740db3fdbe38c0193917570da5c` и кандидатом
`77b0756b140ddbca57858de8bb2896eda0f861d9`.

| Критерий | Проверка | Результат |
|---|---|---|
| Первый сбой schedule Automation повторяется ровно один раз | 6 целевых Go lifecycle/eligibility тестов | PASS |
| Повтор остаётся у исходного worker и не смешивается с ручным/GitHub retry | worker affinity и exclusion тесты | PASS |
| UI показывает queued/running/final failure/disabled/offline | 5 параметризованных UI-проверок | PASS |
| Повтор идемпотентен для completion, lease sweep и переоткрытия БД | lifecycle exactly-once тест | PASS |
| Смежные интерфейсы и сборка не регрессировали | `just build`, 68 UI-тестов, boundary, launcher, tooling, `web/dist` | PASS |

`just check` остановился на существующем `SA4000` в неизменённом
`internal/worker/attempt_lifecycle_test.go`. Отдельный `just test` также выявил
lost-response сбой в неизменённом `internal/worker/worker_integration_test.go`;
целевой `internal/controlplane` и весь UI-набор прошли.

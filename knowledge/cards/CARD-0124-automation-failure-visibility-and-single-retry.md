# CARD-0124 — Провалившийся запуск Automation повторяется один раз

Implementation commit: 700ca82753e9bfd5e71ab1913d3108440aef5749 — Automation автоматически повторяет первый сбой запуска по расписанию у исходного исполнителя и точно показывает итог повтора.

## HEAD

- Статус: Done — реализация влита в `main` работой #215; текущая работа
  закрывает дубликат без повторных продуктовых правок.
- Implementation commit: `700ca82753e9bfd5e71ab1913d3108440aef5749` —
  автоматический retry закреплён за исходным worker, не смешивается с ручным
  GitHub retry и остаётся видимым в интерфейсе.
- Evidence: целевые Go lifecycle/eligibility-сценарии и пять UI-состояний
  повтора присутствуют в реализации; коммит реализации является предком
  актуального `main`.
- Следующее действие: отсутствует; дальнейшая реализация не нужна.

## LOG

### 2026-08-14 — Specification

Владелец подтвердил закрытие как дубликата работы #215: продуктовая поставка
уже слита. Карточка синхронизирована с фактическим implementation commit
`700ca82753e9bfd5e71ab1913d3108440aef5749`; повторно менять код или интерфейс
не требуется.

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

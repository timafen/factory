# CARD-0126: staticcheck для attempt lifecycle

## HEAD

Status: Implemented — доказательства актуализированы
Branch: factory/5db53679-395-298de56e-25c
Implementation commit: c6d8644aaf9700f10365891a30a0679fff45c73b — lifecycle-тест сравнивает результаты двух независимых вычислений задержки и больше не вызывает SA4000
What changed: исправлен lifecycle-тест worker; доказательства фиксируют успешный запуск целевого теста и `staticcheck`. Поведение worker и UI не менялись.
Evidence: `go test ./internal/worker -run '^TestLeaseRenewal'` → код 0; `just staticcheck` → код 0.
One next action: выполнить Review опубликованной поставки.

## LOG

### 2026-08-14 — Implement

Исправлены ссылки на реализацию: указан существующий commit, в котором
lifecycle-тест сопоставляет два независимых вычисления задержки, устраняя
SA4000. Недостоверные ссылки на документационный и отсутствующий commits
удалены; `go test ./internal/worker -run '^TestLeaseRenewal'` и
`just staticcheck` ранее завершились с кодом 0.

### 2026-08-14 — Implement

Заново выполнены целевой lifecycle-тест worker и полный `just staticcheck`:
обе команды завершились с кодом 0. Результат закреплён отдельным commit
реализации lifecycle-теста; product code и UI не менялись.

### 2026-08-14 — Specification

Актуализированы доказательства для уже существующей реализации lifecycle-теста:
на текущей базе целевой lifecycle-тест и полный `just staticcheck` завершились
успешно. Спецификация фиксирует
границы: меняются только документы, а обязательная повторяемая проверка —
`just staticcheck`; browser suite не относится к этой правке.

### 2026-08-13 — Implement

Изменён lifecycle-тест и добавлена спецификация; целевой тест, проектный
`staticcheck`, полный Go-набор и сборка
проходят. Browser suite не объявлялся успешным: запуск блокируется политикой
контейнера.

### 2026-08-13 — Implement

В `internal/worker/attempt_lifecycle_test.go` устранено `SA4000` без изменения product code.
Целевые и полные Go-проверки, staticcheck и сборка прошли; browser suite дошёл до запуска и остановлен контейнерной политикой `no new privileges`.

### 2026-08-13 — Verify

Эта проверка не засчитана: она выполнена до Review текущего HEAD и для прежнего SHA.

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Нет SA4000 в lifecycle-тесте | `just staticcheck` | PASS; анализ `SA*,U1000` всего Go-проекта завершён без замечаний. |
| Lifecycle сохраняет нужные инварианты | `go test ./internal/worker -run '^TestLeaseRenewal'` | PASS; проверены стабильность фазы, lease-бюджет и распределение задержек. |
| Нет изменения product code или UI | pinned diff `99701704b37e8740db3fdbe38c0193917570da5c...48be829a203d721145513ffe376accc60afd8c28` | Из реализации изменён только `internal/worker/attempt_lifecycle_test.go`; также добавлены спецификация и карточка. |
| Полный Go-набор и сборка | `just test`; `just build` | PASS; собраны `factory-server`, `factory-worker`, `factory-release-broker`. |
| Browser suite не выдан за успешный | `just test-browser` | Не засчитан: в чистом контейнере отсутствует `tsc`; запуск Chromium остаётся невозможным по известной политике sandbox. |

### 2026-08-13 — Implement

Карточка возвращена в статус Implemented: прежний Verify относился к старому HEAD и не мог подтверждать текущую поставку.

### 2026-08-13 — Review

Review диапазона `99701704b37e8740db3fdbe38c0193917570da5c...d2eaa3696cb140e68d8889bce64f9286ee29314c` завершён с PASS: исправление сохраняет проверку детерминированности, product code не изменён.

### 2026-08-13 — Verify

Verify выполнен именно для проверенного SHA `d2eaa3696cb140e68d8889bce64f9286ee29314c`.

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Нет SA4000 в lifecycle-тесте | `just staticcheck` | PASS. |
| Lifecycle сохраняет инварианты | `go test ./internal/worker -run '^TestLeaseRenewal'` | PASS. |
| Полный Go-набор | `just test` | PASS. |
| Operator-бинарники собираются | `just build` | PASS. |
| Browser suite не выдан за успешный | `just test-browser` | Не засчитан: `tsc` отсутствует, команда завершилась с exit 127 до Playwright; известная политика контейнера остаётся отдельной блокировкой запуска браузера. |

### 2026-08-13 — Implement

Карточка возвращена в ожидающий статус: `Verified PASS` был снят, потому что доказательства были привязаны к предыдущей версии. Новые Review и Verify должны идти после этого зафиксированного статуса.

### 2026-08-13 — Review

Независимый Review диапазона `99701704b37e8740db3fdbe38c0193917570da5c...dc2a39d90c31f8ea90740e6ad677d35805b696a7` — PASS без замечаний. Правка сохраняет проверку детерминированности, устраняет SA4000 и не меняет product code или UI.

### 2026-08-13 — Verify

Независимый Verify кандида `dc2a39d90c31f8ea90740e6ad677d35805b696a7` — PASS с ограничением среды.

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Нет SA4000 в lifecycle-тесте | `just staticcheck` | PASS, exit 0. |
| Lifecycle сохраняет инварианты | `go test ./internal/worker -run '^TestLeaseRenewal'` | PASS, exit 0. |
| Полный Go-набор | `just test` | PASS, exit 0; выполнен один раз. |
| Operator-бинарники собираются | `FACTORY_BUILD_DIR=/tmp/factory-build-verify.S9jEZH just build` | PASS, exit 0. |
| Browser suite не выдан за успешный | `just test-browser` | Не засчитан: exit 127, `tsc` не найден, Playwright не стартовал; browser sandbox ограничен политикой контейнера. |

### 2026-08-13 — Verify

Verify выполнен для кандидата `a1e8ce70080529f35e05672cccf061b8fd12474e` относительно закреплённой remote-базы `99701704b37e8740db3fdbe38c0193917570da5c`.

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Нет SA4000 в lifecycle-тесте | `just check` (этап `just staticcheck`) | PASS; `SA*,U1000` по всему Go-проекту завершён без замечаний. |
| Lifecycle сохраняет инварианты | `go test ./internal/worker -run '^TestLeaseRenewal'` | PASS, exit 0; детерминированность, lease-бюджет и распределение фаз сохранены. |
| Полный Go-набор и смежные ворота | `just check` | Go format, vet, vulncheck, staticcheck, boundary и `go test ./...` прошли; исходный запуск остановился на отсутствующем `eslint` в чистом checkout. После `just ui-install` команда `just ui-check` прошла: 15 файлов, 173 теста. |
| Operator-бинарники собираются | `FACTORY_BUILD_DIR=/tmp/card0126-build.KLn3Zn just build` | PASS, exit 0; собраны три бинарника. |
| Нет product code или UI в поставке | pinned diff `99701704b37e8740db3fdbe38c0193917570da5c...a1e8ce70080529f35e05672cccf061b8fd12474e` | Ровно три файла: lifecycle-тест, спецификация и карточка; product code и UI не изменены. |
| Browser suite не выдан за успешный | `just test-browser` | FAIL, exit 1: Chromium запущен, 5 тестов прошли; один существующий UI-тест ожидал заголовок «Работа агентов», тогда как страница показывает «Работа», 15 тестов не запускались. UI вне diff; результат записан как смежная краснота, не как PASS. |

# CARD-0126: staticcheck для attempt lifecycle

## HEAD

Status: Verified PASS — awaiting human merge
Branch: factory/b407ea36-0eb-f7cb5256-f32
Implementation commit: 4707a6de747a52c01e5db914f905b4378b3159fe — исправлена проверка стабильной задержки lifecycle-теста
What changed: самосравнение заменено на сравнение двух вычисленных значений `want` и `got`; поведение worker не менялось.
Evidence: independent Review PASS и Verify PASS для `dc2a39d90c31f8ea90740e6ad677d35805b696a7`: `just test`, целевой lifecycle-тест, `just staticcheck` и `just build` завершились с exit 0. Browser suite не засчитан: `just test-browser` завершился до Playwright из-за отсутствующего `tsc` (exit 127); запуск browser sandbox остаётся ограничен политикой контейнера.
One next action: человек подтверждает merge.

## LOG

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

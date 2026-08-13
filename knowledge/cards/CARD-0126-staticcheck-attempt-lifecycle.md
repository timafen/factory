# CARD-0126: staticcheck для attempt lifecycle

## HEAD

Status: Implemented — awaiting Review
Branch: factory/2b530665-c45-529c1cd2-8f6
Implementation commit: 4707a6de747a52c01e5db914f905b4378b3159fe — исправлена проверка стабильной задержки lifecycle-теста
What changed: самосравнение заменено на сравнение двух вычисленных значений `want` и `got`; поведение worker не менялось.
Evidence: реализация закреплена коммитом `4707a6de747a52c01e5db914f905b4378b3159fe`; прежний Verify относился к старому HEAD и не засчитывается.
One next action: провести Review текущего HEAD, затем Verify ровно проверенного SHA.

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

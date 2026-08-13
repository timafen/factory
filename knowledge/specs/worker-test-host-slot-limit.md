# Спецификация: тестовый лимит host-слотов восстанавливает выпускные проверки

## Цель и влияние на владельца

Выпускной конвейер снова должен проходить на машинах с любым числом логических
CPU, не ослабляя защиту production control plane. Сейчас два worker-теста
детерминированно требуют больше активных lease, чем доступно на восьмиядерном
host: startup reconciliation последовательно создаёт 11 попыток в одном Store,
а проверка пула одновременно запускает 10 попыток. После восьмого `Claim`
production-предел из `runtime.NumCPU()` возвращает пустой claim, поэтому свежий
`main` не проходит обязательный `go test -count=1 ./...` и выпуск заперт.

Владелец получит обратно надёжные выпускные ворота. При этом общий runtime-предел
останется равен `runtime.NumCPU()`, worker pool сохранит масштаб 10, а startup
reconciliation продолжит проверять все 11 состояний manifest/filesystem.

## Технический подход и реальные файлы

Фактическая граница находится в `internal/controlplane/store.go`: `Open` записывает
`runtime.NumCPU()` в приватное поле `Store.hostMaxConcurrent`, а `Claim` в
`internal/controlplane/state.go` сравнивает число активных попыток с
`hostSlotLimit()`. Оба падающих теста получают Store через `newServerFixture` из
`internal/worker/worker_integration_test.go`, который вызывает обычный
`controlplane.Open`; из пакета `worker` приватное поле настроить нельзя.

Реализация добавляет в `internal/controlplane/store.go` отдельный явно названный
`OpenForTest(ctx, path, hostMaxConcurrent)` с положительным лимитом. Он использует
тот же путь открытия и миграций, что `Open`, но устанавливает тестовый лимит до
возврата Store вызывающему коду. Конструктор остаётся внутри Go-пакета
`internal/controlplane`: он не получает CLI-флаг, переменную окружения, HTTP/API-
поле или пользовательскую конфигурацию. Нулевое и отрицательное значения
отклоняются, чтобы тест не мог неявно вернуться к production fallback.

В `internal/worker/worker_integration_test.go` рядом с `newServerFixture`
добавляется `newServerFixtureWithHostLimit` для fixture с явным host-лимитом.
Обычный helper и все остальные вызовы продолжают использовать production
`controlplane.Open`. Только `TestCodexWorkerPoolRunsTenAttemptsAndRefillsReleasedSlot`
задаёт лимит 10.
Тест сохраняет 10 одновременно running attempts, разные repository/manifests,
process groups, PID и heartbeat, а одиннадцатую работу получает лишь после
освобождения слота.

В `internal/worker/manifest_integration_test.go` таблица 11 сценариев остаётся
полной; fixture получает явный лимит `len(cases)` после объявления таблицы. Это
связывает доступные lease с числом сценариев и не позволяет молча добавить case,
который снова упрётся в host CPU. Lifecycle, retention, cleanup, worktree и branch
assertions каждого сценария не меняются.

В `internal/controlplane/store_test.go` новый тест фиксирует границу API: test-only
открытие принимает и применяет явное положительное значение, отклоняет
неположительное, а обычный `Open` по-прежнему получает `runtime.NumCPU()`. Логику
`Claim` в `internal/controlplane/state.go`, production-документацию и настройки
воркера менять не требуется.

## Последовательный план

1. Добавить test-only открытие Store с обязательным положительным лимитом,
   переиспользовав существующий `openStore` и не меняя контракт обычного `Open`.
2. Закрепить unit-тестом явный тестовый лимит, валидацию и неизменный production
   default `runtime.NumCPU()`.
3. Добавить worker fixture-helper, который выбирает test-only открытие до создания
   HTTP handler; существующий `newServerFixture` оставить на production-пути.
4. Перевести только тест пула на лимит 10, не меняя количество attempts,
   repositories, процессов, heartbeat и проверку дозаполнения слота.
5. Перевести только startup reconciliation на лимит `len(cases)`, сохранив все 11
   именованных cases и их исходные assertions.
6. Выполнить каждый из двух регрессионных тестов отдельно без cache, затем один
   полный uncached-прогон `./...`; повторять полный набор на итерациях не нужно.

## Критерии приёмки

1. `TestStartupReconciliationClassifiesManifestAndFilesystemState` проходит на
   host с восемью CPU и выполняет ровно все 11 текущих subtest: ни один case или
   lifecycle/worktree/branch assertion не удалён и не ослаблен.
2. `TestCodexWorkerPoolRunsTenAttemptsAndRefillsReleasedSlot` одновременно доводит
   до running ровно 10 attempts, наблюдает их manifests, разные process groups,
   runtime PID и heartbeat, завершает их и запускает одиннадцатую работу в
   освобождённом слоте.
3. Обычный `controlplane.Open` и fallback прямого Store сохраняют предел
   `max(1, runtime.NumCPU())`; `Claim` и его подсчёт host-wide активных lease не
   меняются.
4. Override доступен только как явно test-only API пакета `internal/controlplane`,
   применяется до публикации handler и отсутствует в CLI, HTTP, environment,
   protocol и production call sites.
5. Каждый целевой тест проходит отдельным uncached-запуском, а затем полный
   `go test -count=1 ./...` проходит с первого запуска.

## Тест-план

- `internal/controlplane/store_test.go`: проверить явный лимит test-only Store,
  ошибку для `0`/отрицательного значения и неизменный предел обычного `Open`.
- Отдельно выполнить
  `go test -count=1 -run '^TestStartupReconciliationClassifiesManifestAndFilesystemState$' ./internal/worker`.
- Отдельно выполнить
  `go test -count=1 -run '^TestCodexWorkerPoolRunsTenAttemptsAndRefillsReleasedSlot$' ./internal/worker`.
- После целевых итераций ровно один раз выполнить полный выпускной барьер
  `go test -count=1 ./...` и зафиксировать exit code 0.
- Проверить поиском production call sites: test-only конструктор упоминается
  только в `*_test.go`; выполнить `git diff --check`.

## Риски и решения

- Test-only функция всё равно компилируется в Go-пакет. Область `internal/`
  запрещает внешнее использование, имя явно маркирует назначение, а отсутствие
  CLI/API/env-провода и production call sites не даёт владельцу обойти предел.
- Настройка Store после запуска handler создала бы гонку. Конструктор принимает
  лимит до возврата Store, а fixture создаёт handler только после открытия.
- Жёсткая константа 11 снова устареет при расширении таблицы. Reconciliation
  использует `len(cases)` и поэтому сохраняет соответствие числа lease всем cases.
- Слишком большой общий fixture-limit мог бы скрыть ошибку пула. Pool-тест задаёт
  ровно 10, чтобы одиннадцатая попытка требовала освобождения слота, как и раньше.
- Уменьшение пула или удаление reconciliation cases ускорило бы зелёный результат,
  но потеряло бы контракты CARD-0055/CARD-0096; такой вариант исключён.

## Карточка работы

`knowledge/cards/CARD-0153-worker-test-host-slot-limit.md`

Номер CARD-0153 проверен свободным в свежем `origin/main` и tip всех 927
опубликованных веток; CARD-0098 остаётся неизменяемым связанным контрактом
production host budget.

Ниже зафиксирован машинно проверяемый контракт передачи в Implement: четыре
строки `файл` исчерпывают разрешённую область продуктовых изменений, а строка
`команда` одновременно запускает новый тест test-only API и обе исходные
регрессии. Реализация считается готовой только при коде завершения 0 этой
команды; одно лишь ручное подтверждение или зелёный запуск части тестов условие
не выполняет.

ГОТОВО-КОГДА: файл internal/controlplane/store.go
ГОТОВО-КОГДА: файл internal/controlplane/store_test.go
ГОТОВО-КОГДА: файл internal/worker/worker_integration_test.go
ГОТОВО-КОГДА: файл internal/worker/manifest_integration_test.go
ГОТОВО-КОГДА: команда go test -count=1 -run '^(TestTestingHostSlotLimitIsExplicitAndProductionDefaultUnchanged|TestStartupReconciliationClassifiesManifestAndFilesystemState|TestCodexWorkerPoolRunsTenAttemptsAndRefillsReleasedSlot)$' ./internal/controlplane ./internal/worker

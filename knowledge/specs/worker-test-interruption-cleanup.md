# Прерывание worker-тестов не оставляет процессы и `/tmp`

## Цель и влияние на владельца

Оборванный прогон `go test` в пакете worker не должен оставлять в машине
блокирующий fake `gh`, его отдельную process group или временный корень теста.
Владелец сможет безопасно останавливать локальные и CI-прогоны без накопления
сиротских процессов и каталогов в `/tmp`.

Гарантия действует, когда контролируемый test-helper получает `TERM`, `INT` или
`HUP`: он завершает все process group, которые сам создал, и удаляет свой
отдельный временный корень. `SIGKILL` не входит в гарантию: процесс после него
не может выполнить cleanup без внешнего supervisor. Уже накопленные каталоги,
production-семантика `gh`/clone и release-тесты не меняются.

## Технический подход и реальные файлы

`internal/worker/repository_coordination_test.go` создаёт fake `gh`, который в
режимах `block-first` и `block-all` ждёт файл `release`; `acquireManagedAsync`
передаёт в production-путь `context.Background()`. В
`internal/worker/command.go` `runCommand` через `configureNewProcessGroup`
запускает такую команду в отдельной группе, поэтому прекращение только
родительского test-процесса не очищает группу при внешнем прерывании теста.

В `internal/worker/worker_integration_test.go` расположен `TestMain`, а
`internal/worker/test_interruption_unix_test.go` содержит test-only lifecycle:
он создаёт изолированный `MkdirTemp`-корень, регистрирует каждый PID/process
group существующего blocking fake `gh`, ловит
`TERM`, `INT`, `HUP`, посылает группе `TERM` с ограниченным ожиданием и затем
`KILL` при необходимости, ожидает дочерние процессы и вызывает `RemoveAll`.
Сигналы и проверка group будут использовать имеющиеся unix-помощники
`internal/worker/platform_unix.go`; Windows в scope не входит.

Регрессия из `internal/worker/repository_coordination_test.go` стартует
отдельный контролируемый `go test` с реальным managed-clone сценарием
`block-all`, дождётся файла `first.started` и
записанных PID/PGID, пошлёт ему каждый из `TERM`, `INT`, `HUP`, дождётся выхода
и проверит отсутствующие PID/process group и корень. Она не будет полагаться на
таймаут тестового раннера или на release-файл. Существующие сценарии managed
repository и проверки process group останутся без ослабления.

## Последовательный план

1. Выделить test-only lifecycle helper с приватным temp-root и реестром групп,
   не затрагивая `runCommand` и production-код.
2. До запуска блокирующего fake `gh` передавать helper-у наблюдаемые PID/PGID;
   на `TERM`/`INT`/`HUP` последовательно остановить, reap-нуть и удалить root.
3. Добавить дочерний controlled-run режим и table-driven регрессию для трёх
   сигналов; дождаться маркера блокировки до отправки сигнала.
4. Проверить, что после controlled run `kill(-pgid, 0)` сообщает отсутствие
   группы, PID больше не существует, а `os.Stat(tempRoot)` даёт `ENOENT`.
5. Запустить целевые worker-тесты, затем один полный Go-набор.

## Критерии приёмки

- Контролируемый interrupted-run с blocking fake `gh` очищает PID, его process
  group и выделенный тестовый temp-root после каждого из `TERM`, `INT`, `HUP`.
- Уборщик посылает группам сигнал как группе, ждёт завершения и имеет ограниченный
  fallback, чтобы сама регрессия не оставляла процесс при неудаче assertion.
- `SIGKILL` явно документирован как исключение без внешнего supervisor.
- Обычное получение managed repository, отмена clone и существующие worker
  process-group сценарии продолжают проходить.
- В diff нет изменения production-файлов или удаления старого мусора `/tmp`.

## Тест-план

Сначала выполнить новую регрессию вместе с координационными сценариями:

```sh
go test ./internal/worker -run 'Test(WorkerTestInterruptionCleanup|UnrelatedManagedRepositoryClonesOverlap|BlockedCloneDoesNotPreventCachedRepositoryAcquisition|DuplicateManagedRepositoryAcquisitionClonesOnce|CancelledManagedRepositoryCloneReleasesCoordination|TimeoutStopsIgnoringProcessGroup)$'
```

Она должна для каждого сигнала подтвердить запуск fake `gh`, исчезновение PID и
PGID и отсутствие temp-root. Затем выполнить единственный полный набор:

```sh
go test -timeout 5m ./...
```

## Риски и решения

- Сигнальная регрессия может быть flaky, если послать сигнал до запуска `gh`.
  Решение: синхронизироваться файловым маркером и PID/PGID, а не sleep.
- PID может быть переиспользован. Решение: проверять group сразу после выхода и
  хранить identity/ожидать reaping, используя уже существующую защиту platform.
- `t.TempDir()` cleanup не запускается после смерти test-процесса. Решение:
  controlled helper владеет отдельным `MkdirTemp` и удаляет его в signal path.
- Нельзя обещать cleanup после `SIGKILL`. Решение: ограничить контракт
  перехватываемыми сигналами и не вводить непроверяемый внешний демон.

## Карточка работы

`knowledge/cards/CARD-0097-worker-test-interruption-cleanup.md`

ГОТОВО-КОГДА: файл internal/worker/repository_coordination_test.go
ГОТОВО-КОГДА: файл internal/worker/worker_integration_test.go
ГОТОВО-КОГДА: файл internal/worker/test_interruption_unix_test.go
ГОТОВО-КОГДА: команда go test ./internal/worker -run 'TestWorkerTestInterruptionCleanup$'

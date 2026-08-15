# Прерывание worker-тестов не оставляет процессы и `/tmp`

## Цель и влияние на владельца

Оборванный прогон `go test` в пакете worker не должен оставлять на машине
блокирующий fake `gh`, его отдельную process group или временный корень теста.
Владелец сможет безопасно останавливать локальные и CI-прогоны без накопления
сиротских процессов и каталогов в `/tmp`, мешающих следующим запускам.

Гарантия действует, когда контролируемый test-helper получает `TERM`, `INT` или
`HUP`: он завершает все process group, которые сам создал, и удаляет свой
отдельный временный корень. `SIGKILL` не входит в гарантию: убитый процесс не
может выполнить cleanup без внешнего supervisor. Уже накопленный мусор,
production-семантика `gh`/clone и release-тесты не меняются.

## Технический подход и реальные файлы

`internal/worker/repository_coordination_test.go` создаёт fake `gh`, который в
режимах `block-first` и `block-all` ждёт файл `release`; `acquireManagedAsync`
передаёт в production-путь `context.Background()`. В
`internal/worker/command.go` функция `runCommand` через существующий
`configureNewProcessGroup` запускает команду в отдельной группе. Поэтому внешний
сигнал родительскому test-процессу не отменяет acquisition и сам по себе не
очищает дочернюю группу.

В существующий `TestMain` из
`internal/worker/worker_integration_test.go` добавляется test-only lifecycle для
контролируемого дочернего прогона. Unix-реализация в новом
`internal/worker/test_interruption_unix_test.go` ставит обработчики `TERM`,
`INT`, `HUP` до `main.Run`, ведёт реестр PID/process group блокирующих fake
инструментов, посылает каждой группе `TERM`, ограниченно ждёт и применяет `KILL`
только как fallback. После reaping дочерних команд helper удаляет принадлежащий
ему `MkdirTemp`-корень. Для сигналов и проверки групп переиспользуются имеющиеся
помощники `internal/worker/platform_unix.go`; production-файлы не меняются.

Регрессия в `internal/worker/repository_coordination_test.go` запускает отдельный
контролируемый `go test` с настоящим managed-clone сценарием `block-all`, ждёт
`first.started` и записанных PID/PGID, по очереди посылает helper-процессу каждый
из трёх сигналов, дожидается его выхода и проверяет отсутствие PID, process group
и temp-root. Проверка не зависит от таймаута тестового раннера или создания файла
`release`; аварийный cleanup самой регрессии не даст ей оставить процессы при
неудачном assertion.

## Последовательный план

1. Выделить unix test-only lifecycle helper с приватным temp-root и реестром
   созданных process group, не меняя `runCommand` и production-код.
2. Установить signal handler до `main.Run`; до публикации readiness передавать
   helper-у наблюдаемые PID/PGID реального blocking fake `gh`.
3. На `TERM`, `INT`, `HUP` завершать зарегистрированные группы по схеме
   TERM → ограниченное ожидание → KILL, дождаться `Cmd.Wait` и удалить root.
4. Добавить table-driven controlled-run регрессию для трёх сигналов и
   синхронизировать её файловыми маркерами вместо `sleep`.
5. Сохранить существующие managed-repository и process-group assertions,
   выполнить целевой набор, а полный Go-набор оставить единственному Verify.

## Критерии приёмки

- Для каждого из `TERM`, `INT`, `HUP` контролируемый interrupted-run с реальным
  `block-all` fake `gh` завершается с кодом 0 после обработки сигнала.
- После выхода helper PID fake `gh` и его process group не существуют, а
  выделенный тестовый temp-root возвращает `ENOENT` при `os.Stat`.
- Уборщик сигналит именно группе, ждёт production `Cmd.Wait` и имеет
  ограниченный TERM→KILL fallback; cleanup регрессии также ограничен по времени.
- `SIGKILL` документирован как исключение без внешнего supervisor.
- Обычное получение managed repository, отмена clone и существующий сценарий
  остановки игнорирующей сигнал process group продолжают проходить.
- В реализации нет изменений production-файлов и удаления ранее накопленного
  содержимого `/tmp`.

## Тест-план

На Implement выполнить новую регрессию вместе с соседними сценариями:

```sh
go test ./internal/worker -run 'Test(WorkerTestInterruptionCleanup|UnrelatedManagedRepositoryClonesOverlap|BlockedCloneDoesNotPreventCachedRepositoryAcquisition|DuplicateManagedRepositoryAcquisitionClonesOnce|CancelledManagedRepositoryCloneReleasesCoordination|TimeoutStopsIgnoringProcessGroup)$'
```

Регрессия обязана для каждого сигнала подтвердить запуск blocking fake `gh`,
исчезновение PID/PGID и отсутствие temp-root. На Verify ровно один раз выполнить
полный набор:

```sh
go test -timeout 5m ./...
```

## Риски и решения

- Сигнал может прийти до установки обработчика или запуска fake `gh`. Решение:
  ставить handler до `main.Run`, а родителя синхронизировать readiness-файлом,
  опубликованным только после записи PID/PGID.
- PID может быть переиспользован. Решение: сразу после reaping проверять PID и
  группу; при остановке использовать уже существующую проверку identity там, где
  lifecycle располагает ею.
- `t.TempDir()` cleanup не запускается после смерти test-процесса. Решение:
  controlled helper владеет отдельным `os.MkdirTemp` и явно удаляет его в
  signal-path после остановки групп.
- Ошибка assertion сама может оставить helper. Решение: parent-регрессия
  регистрирует ограниченный cleanup с остановкой всей controlled process group.
- Нельзя обещать cleanup после `SIGKILL`. Решение: ограничить контракт
  перехватываемыми сигналами и не вводить непроверяемый внешний демон.

## Карточка работы

`knowledge/cards/CARD-0097-worker-test-interruption-cleanup.md`

ГОТОВО-КОГДА: файл internal/worker/repository_coordination_test.go
ГОТОВО-КОГДА: файл internal/worker/worker_integration_test.go
ГОТОВО-КОГДА: файл internal/worker/test_interruption_unix_test.go
ГОТОВО-КОГДА: команда go test ./internal/worker -run 'TestWorkerTestInterruptionCleanup$'

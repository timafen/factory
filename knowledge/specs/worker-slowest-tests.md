# Спецификация: ускорить самые медленные тесты воркера без потери покрытия

## Goal and user impact

Разработчики и выпускной конвейер будут быстрее получать результат Go-проверок
воркера. Четыре самых долгих воспроизводимых сценария сохранят все проверяемые
состояния, количество конкурентных попыток и настоящие Git-операции, но перестанут
тратить время на повторную подготовку одинаковых фикстур и последовательное
исполнение независимых случаев.

Контрольный запуск от 10 августа 2026 года без test cache занял 215,22 с. Четыре
главных цели: `TestServerLossStopsCodexBeforeLeaseExpiry` — 41,28 с,
`TestCodexWorkerPoolRunsTenAttemptsAndRefillsReleasedSlot` — 20,48 с,
`TestTimeoutStopsIgnoringProcessGroup` — 16,03 с и
`TestStartupReconciliationClassifiesManifestAndFilesystemState` — 14,49 с. Цель —
их совместный целевой запуск укладывается в 35 секунд на том же worker host.

## Technical approach

Минимальное изменение ограничено тестовой инфраструктурой `internal/worker`:

- В `internal/worker/worker_integration_test.go` подготовить неизменяемый Git-
  шаблон с одним начальным коммитом и создавать из него отдельные checkout и bare
  origin для `createRepository`. У каждого вызова остаются собственные пути,
  origin identity, ветка `main` и удалённый репозиторий; тесты по-прежнему выполняют
  реальные `git clone`, `fetch`, `push`, worktree и cleanup. Содержимое начального
  коммита не участвует в assertions и может быть общим.
- Там же оставить тест пула в исходном масштабе: 10 одновременно занятых слотов,
  один queued task, 11 разных repository identities, отдельные manifests,
  supervisor process groups и runtime PID, отмена одного task, дозаполнение
  освободившегося слота и успешное завершение остальных попыток.
- В `TestServerLossStopsCodexBeforeLeaseExpiry` после подтверждения работающего
  дочернего процесса передать его supervisor короткое последнее lease renewal
  через существующий test-visible `supervisorProcess.renew`, а затем закрыть сервер.
  Так проверяется тот же автономный stop на истечении последней аренды, но тест не
  ждёт штатные 30 секунд `protocol.LeaseDuration`; отдельная проверка до короткого
  deadline не даст тесту превратиться в немедленное убийство процесса.
- В `TestTimeoutStopsIgnoringProcessGroup` сократить task timeout после ускорения
  Git-setup, сохранив настоящий timer воркера, игнорирующий SIGTERM дочерний процесс,
  переход попытки в `failed`, ошибку `timeout` и проверку исчезновения process group.
- В `internal/worker/manifest_integration_test.go` поднять неизменяемые server/store
  и repository fixture из 11 последовательных подслучаев
  `TestStartupReconciliationClassifiesManifestAndFilesystemState` на уровень
  родительского теста. У каждого случая остаются отдельные manager, data/worktree
  directories, task и manifest. Параллельный запуск отклонён: `newTestManager`
  использует process-wide test environment, несовместимый с `t.Parallel()`.

Production-код, публичные API, схема БД, конфигурация и формат manifest не меняются.

## Plan

1. Добавить пакетную test-фикстуру неизменяемого Git-шаблона с гарантированной
   очисткой и перевести `createRepository` на создание независимых клонов шаблона.
2. Сохранить уникальные имена каталогов и origin каждого repository fixture и
   прогнать тесты, которые меняют remote, refspec, ветки и публикуют коммиты.
3. Переиспользовать server/store и repository только внутри последовательной
   таблицы startup reconciliation; подтвердить уникальность task, manifest и
   worktree каждого случая и отсутствие состояния от предыдущего случая.
4. В server-loss сценарии сократить последнюю аренду через штатный supervisor
   renewal; в timeout-сценарии подобрать минимальный устойчивый task timeout по
   пяти uncached-прогонам на worker host.
5. Выполнить целевые функциональные прогоны и обязательный временной барьер; полный
   `go test ./...` оставить единственному прогону стадии Verify.

## Acceptance criteria

1. `TestCodexWorkerPoolRunsTenAttemptsAndRefillsReleasedSlot` по-прежнему доказывает,
   что воркер одновременно запускает 10 попыток в 10 разных репозиториях, держит
   одиннадцатую в очереди, после отмены заполняет слот и не смешивает manifests,
   worktrees, supervisor groups или runtime processes.
2. Все 11 именованных случаев
   `TestStartupReconciliationClassifiesManifestAndFilesystemState` выполняются и
   подтверждают прежние lifecycle, retention, cleanup, worktree и branch outcomes.
3. Каждый `createRepository` возвращает отдельные checkout и bare origin с веткой
   `main`, доступным начальным коммитом и уникальной remote identity; изменения и
   публикация в одной фикстуре не меняют другую.
4. Совместный uncached-запуск четырёх целевых тестов завершается успешно не позднее
   35 секунд на штатном worker host; функциональный сбой также даёт ненулевой код.
5. Server-loss проверяет, что дочерняя process group живёт до потери последней
   аренды, исчезает после неё, а sweep помечает попытку `lost`; timeout-сценарий
   по-прежнему проходит через настоящий task timer и завершает попытку как failed.
6. В production-файлах, API, конфигурации, миграциях и runtime-поведении изменений
   нет, а ни один test case или assertion не удалён и не ослаблен.

## Test plan

- Добавить в `internal/worker/worker_integration_test.go` регрессию изоляции двух
  репозиториев, созданных из общего шаблона: разные origin identities, независимые
  refs и отсутствие опубликованного в одном репозитории коммита во втором.
- Локально при реализации прогнать тесты фикстуры и чувствительные Git-сценарии:
  `go test -count=1 -run 'Test(RepositoryFixturesFromTemplateAreIsolated|WorktreeUsesRemoteDefaultBranchWithoutChangingCheckout|WorktreeFetchDoesNotApplyConfiguredOriginRefmap)$' ./internal/worker`.
- Отдельно по пять раз прогнать server-loss и task-timeout сценарии, проверяя не
  только длительность, но и прежние terminal state и process-group assertions.
- Затем выполнить обязательный барьер скорости и покрытия:
  `timeout 35s go test -count=1 -run 'Test(ServerLossStopsCodexBeforeLeaseExpiry|CodexWorkerPoolRunsTenAttemptsAndRefillsReleasedSlot|TimeoutStopsIgnoringProcessGroup|StartupReconciliationClassifiesManifestAndFilesystemState)$' ./internal/worker`.
- На Verify ровно один раз выполнить полный набор: `go test -count=1 ./...`.

## Risks and decisions

- Порог времени зависит от нагрузки host. 35 секунд оставляет значительный запас
  относительно исходных 92,28 с четырёх целей, но не должен подменять функциональные
  assertions; при нестабильности на штатном host владелец должен согласовать более
  широкий порог на основании серии минимум из пяти uncached-прогонов.
- Общий шаблон обязан оставаться неизменяемым. Клонирование создаёт независимые
  origin и checkout; прямое совместное использование одного origin отклонено,
  потому что оно сократило бы проверку repository-level concurrency и изоляции.
- Уменьшение числа repositories, slots, manifests, процессов или табличных случаев
  отклонено как сокращение покрытия.
- Подмена supervisor timer сном или прямым убийством процесса отклонена: короткое
  renewal использует тот же production path и сохраняет проверку автономного
  завершения после потери сервера. Timeout меньше устойчивого по пяти прогонам
  внедрять нельзя.
- Изменение production Git-кода ради скорости тестов и новый внешний test tool
  отклонены как лишний scope. Человеческого согласования перед реализацией не
  требуется, если сохраняются указанные масштаб, assertions и временной порог.

## Card

`knowledge/cards/CARD-0055-worker-slowest-tests.md`

Карточку создаёт стадия Implement после отдельного коммита реализации, чтобы её
первая строка могла содержать существующий полный `Implementation commit`.

## Проверяемые обещания

ГОТОВО-КОГДА: файл internal/worker/worker_integration_test.go
ГОТОВО-КОГДА: файл internal/worker/manifest_integration_test.go
ГОТОВО-КОГДА: команда timeout 35s go test -count=1 -run 'Test(ServerLossStopsCodexBeforeLeaseExpiry|CodexWorkerPoolRunsTenAttemptsAndRefillsReleasedSlot|TimeoutStopsIgnoringProcessGroup|StartupReconciliationClassifiesManifestAndFilesystemState)$' ./internal/worker

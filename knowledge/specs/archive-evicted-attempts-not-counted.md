# Спецификация: архивные вытесненные попытки не занимают лимит

## Цель и влияние на владельца

Владелец видит полную историю попыток и может воспользоваться архивной записью
вытесненной попытки, но такая запись не блокирует новый запуск по лимиту
репозитория. Воркеры не застревают на ложном `MaxRetainedPerRepo`, пока архив
растёт; реально сохранённые worktree по-прежнему учитываются и требуют cleanup.

## Технический подход и реальные файлы

Сейчас история задачи в `internal/controlplane/store.go` возвращает все строки
`attempts`, а допуск к маршрутизации и claim в `internal/controlplane/state.go`
и `store.go` складывает `worker_repositories.retained_count`, активные попытки
и terminal-попытки с `capacity_acknowledged = 0`. Поле подтверждения нужно
использовать только для незавершённой передачи capacity, а не для уже
вытесненной архивной попытки.

Реализация должна сохранить terminal-строку и её результат в API истории,
отделить её от фактического retained worktree и исключить архивную запись из
производного `retentionUse` после фиксации вытеснения. В SQL-предикатах должен
остаться строгий учёт `preparing`/`running`, `worker_repositories.retained_count`
и только ещё не подтверждённых terminal-переходов. Один и тот же предикат
применяется в claim, выборе маршрута, `WorkerRepositoryOptions` и
`ManagedRepositoryReadiness`; `COALESCE` сохраняет корректный нулевой счётчик.

Транзакция регистрации продолжает подтверждать `capacity_acknowledged` для
вытесненной попытки, а API `Task` продолжает возвращать её в `Attempts`. Не
удалять строки attempts, не менять wire-модель и не править `web/`; retained
worktree и его cleanup-команда остаются видимыми владельцу.

Реальные файлы реализации:

- `internal/controlplane/state.go` — допуск claim с единым фильтром capacity.
- `internal/controlplane/store.go` — маршрутизация и readiness без двойного
  учёта архивной попытки; регистрация сохраняет историю и подтверждение.
- `internal/controlplane/store_test.go` — серверная regression-проверка
  вытесненной terminal-попытки, сохранённой истории и нового допуска.

## Последовательный план

1. Зафиксировать существующий жизненный цикл: terminal attempt остаётся в
   `Task.Attempts`, retained summary остаётся в регистрации, а подтверждение
   передачи меняет только capacity-состояние.
2. Вынести/согласовать предикат производного repository retention use и
   заменить им все четыре SQL-пути: claim, route, repository options и
   readiness. Не считать архивную, уже подтверждённую попытку.
3. Добавить тест с лимитом `MaxRetainedPerRepo`: создать и завершить попытку,
   зарегистрировать её как вытесненную, проверить сохранение строки истории и
   успешно назначить следующую задачу тому же репозиторию.
4. Добавить отрицательные проверки: живой worktree и terminal-передача с
   `capacity_acknowledged = 0` продолжают блокировать лимит; повторная
   регистрация не создаёт новый учёт.
5. Запустить обязательный целевой тест, проверить форматирование и границы
   документационной поставки.

## Критерии приёмки

1. После вытеснения архивная попытка доступна в `GET /api/v1/tasks/{id}` с
   прежним state/result/error и не удаляется из `attempts`.
2. При освобождённом фактическом retained capacity следующая задача того же
   репозитория получает claim/route, даже если архив содержит вытесненную
   попытку.
3. Активная попытка, retained worktree и terminal-попытка с неподтверждённой
   передачей capacity по-прежнему считаются и не допускают переполнения лимита.
4. Claim, обычный route, `WorkerRepositoryOptions` и readiness возвращают
   одинаковый derived retention use.
5. UI, формат ответа попытки и удаление истории не меняются.

## Тест-план

- `go test ./internal/controlplane -run 'Test(RoutedTaskExcludesWorkersWithoutRepositoryCapacity|TerminalAttemptReservesRetainedHeadroomUntilRegistration|ArchivedEvictedAttemptDoesNotConsumeRepositoryCapacity)$'` — новый тест должен подтвердить именно сохранение архива и повторный допуск.
- В `internal/controlplane/store_test.go` проверить три состояния: retained,
  unacknowledged terminal и acknowledged archived terminal; сравнить число
  attempts, `retained_count` и назначенного worker.
- Повторно прогнать тот же тест после повторной регистрации, чтобы исключить
  двойное уменьшение/увеличение счётчика.
- Перед передачей выполнить `git diff --check` и проверить трёхточечный список
  файлов относительно свежего `origin/main`.

## Риски и решения

- Риск преждевременного освобождения capacity: считать попытку архивной только
  после транзакционного подтверждения `capacity_acknowledged` и сохранять
  отдельный `retained_count` для реально оставшегося worktree.
- Риск расхождения SQL-путей: использовать один именованный helper/фрагмент
  или эквивалентный предикат, покрытый тестами claim и route/readiness.
- Риск потери истории: не делать `DELETE` и не фильтровать `Task.Attempts`;
  архивная видимость является частью контракта.
- Риск несовместимости старого worker: оставить существующие поля регистрации
  и идемпотентное подтверждение по ID.

## Карточка работы

`knowledge/cards/CARD-0127-archive-evicted-attempts-not-counted.md`

ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл internal/controlplane/store.go
ГОТОВО-КОГДА: файл internal/controlplane/store_test.go
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run 'Test(RoutedTaskExcludesWorkersWithoutRepositoryCapacity|TerminalAttemptReservesRetainedHeadroomUntilRegistration)$'

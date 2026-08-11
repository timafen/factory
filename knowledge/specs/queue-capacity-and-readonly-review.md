# Спецификация: очередь использует свободных совместимых исполнителей

## Цель

Задача не должна ждать первоначально выбранного worker, если другой здоровый
worker свободен и совместим по runtime и репозиторию. Review может идти рядом с
writer только как read-only работа по зафиксированному снимку.

## Контракт

- Claim выбирает старейшее queued execution, совместимое с запрашивающим worker
  по runtime, advertised repository, общей capacity и retained capacity.
- В той же транзакции execution переназначается и переводится в `preparing` до
  создания ответа. Условный переход и уникальный active attempt исключают дубли.
- Несовместимый worker получает пустой claim. После появления совместимости новый
  poll повторяет проверку; это состояние «ещё не готово», а не ошибка задачи.
- Ревизия Workflow хранит `read_only`; задача и claim получают неизменяемый
  snapshot признака. Такой worker читает отдельный worktree на committed base,
  не меняет данные и сообщает `NOT READY`, если нужного commit ещё нет.
- Overview API сообщает `queue_reassignments` для выбранного окна.

## Критерии приёмки и тесты

1. Свободный совместимый worker забирает очередь другого worker, а назначение и
   метрика обновляются — `TestCompatibleIdleWorkerClaimsQueuedAssignment`.
2. Два параллельных claim создают один attempt; уже работающий writer не
   останавливается — `TestCompatibleWorkersClaimOnceWhileWriterContinues`.
3. Несовместимость repository оставляет задачу queued, а последующая регистрация
   делает её доступной — `TestQueuedAssignmentRejectsIncompatibleWorkers`.
4. `read_only` сохраняется из Workflow в Task и Claim, а prompt закрепляет
   committed snapshot / non-blocking / `NOT READY` —
   `TestReadOnlyWorkflowMetadataIsSnapshottedIntoClaims` и
   `TestReadOnlyClaimCarriesCommittedSnapshotRule`.

## Вне области

Не менять lease duration, worker capacity, retry policy завершившихся попыток,
изоляцию worktree и алгоритм первоначального выбора worker при создании задачи.

## Проверяемые обещания

ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл migrations/023_queue_reassignment.sql
ГОТОВО-КОГДА: файл internal/controlplane/store_test.go
ГОТОВО-КОГДА: файл internal/controlplane/workflows_test.go
ГОТОВО-КОГДА: файл internal/worker/prompt_test.go
ГОТОВО-КОГДА: команда go test ./internal/controlplane ./internal/worker

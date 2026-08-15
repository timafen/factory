# Спецификация: очередь не простаивает при свободном совместимом исполнителе

## Цель и влияние на владельца

Когда исходно назначенный исполнитель занят, работа больше не ждёт именно его:
свободный здоровый исполнитель забирает её, если у него тот же runtime и
рекламируется нужный репозиторий. Владелец получает более короткое ожидание без
ручного переназначения и видит число таких переносов в обзоре за 24 часа.

## Технический подход и реальные файлы

- `internal/controlplane/state.go` выбирает старейший `queued` execution по
  runtime и доступному репозиторию запрашивающего worker, затем в одной
  транзакции создаёт attempt, переводит execution в `preparing`, меняет
  `assigned_worker_id` и записывает событие переназначения.
- `internal/controlplane/store.go`, `workflows.go` и
  `internal/protocol/types.go` сохраняют `read_only` из ревизии Workflow в
  неизменяемый snapshot Task/Claim.
- `migrations/024_queue_reassignment.sql` и
  `migrations/025_queue_reassignment_events.sql` добавляют счётчик и журнал
  событий; `internal/controlplane/metrics.go` считает только события, попавшие
  в запрошенное окно.
- `internal/worker/attempt_lifecycle.go` возвращает read-only Review с
  `NOT READY` структурированно, а `internal/controlplane/work_resume_http.go`
  повторно ставит тот же execution в очередь без второго активного attempt.
- `internal/worker/prompt_test.go` закрепляет правило: Review читает committed
  snapshot, не ждёт и не блокирует writer.
- `web/src/Overview.tsx`, `web/src/Overview.test.ts`, `web/src/types.ts` и
  тестовые fixtures выводят 24-часовую метрику переназначений.

## Последовательный план

1. Сохранить фильтр claim по runtime, advertised repository, capacity и
   retained capacity именно запрашивающего worker, не фильтруя по первоначально
   назначенному worker.
2. Выполнять выбор, смену назначения, создание attempt и запись события в одной
   транзакции с условным переходом только из `queued`.
3. Сохранять `read_only` в ревизии Workflow и Task, передавать его в Claim и
   повторно ставить read-only Review в очередь при `NOT READY`.
4. Считать обзорную метрику по времени событий, а не по `updated_at` execution,
   и показать её в UI.
5. Закрепить сценарии совместимости, гонки, повторной проверки и read-only
   snapshot целевыми тестами.

## Критерии приёмки

1. Свободный совместимый worker забирает ожидающую работу другого worker, а
   назначение и `queue_reassignments` обновляются.
2. Два одновременных claim создают ровно один attempt; уже выполняющийся writer
   продолжает работу.
3. Несовместимый repository или runtime возвращает пустой claim и не меняет
   queued execution; после регистрации совместимости следующий poll забирает
   ту же работу.
4. `read_only` является snapshot ревизии: Claim требует committed snapshot,
   не блокирует writer, а `NOT READY` завершает попытку и возвращает execution
   в `queued` без дубля.
5. Метрика учитывает только фактические переназначения в заданном временном
   окне и доступна на экране обзора.

## Тест-план

- `TestCompatibleIdleWorkerClaimsQueuedAssignment` проверяет перенос на
  свободного совместимого worker и метрику.
- `TestCompatibleWorkersClaimOnceWhileWriterContinues` проверяет гонку claim и
  непрерывность writer.
- `TestQueuedAssignmentRejectsIncompatibleWorkers` проверяет пустой claim и
  доступность после регистрации repository.
- `TestReadOnlyWorkflowMetadataIsSnapshottedIntoClaims`,
  `TestReadOnlyClaimCarriesCommittedSnapshotRule` и
  `TestReadOnlyNotReadyIsRequeuedWithoutDuplicateAttempt` проверяют snapshot и
  повторную постановку Review.
- `TestMetricsCountQueueReassignmentsByEventTime` проверяет границы окна
  событий; UI-тест Overview проверяет отображение метрики.

## Риски и решения

- Гонка двух poller может создать дублирующий attempt — условный `UPDATE` из
  `queued` и транзакция оставляют победителя только одного.
- Исполнитель с другим repository может случайно взять работу — join по
  advertised repository и runtime возвращает ему пустой claim.
- Позднее обновление execution может исказить метрику — журнал
  `execution_reassignments.reassigned_at` отделяет время события от обновления.
- Read-only Review может ждать незакоммиченные данные — prompt задаёт
  non-blocking правило и маршрут `NOT READY` для следующей проверки.

## Карточка работы

Отдельная карточка: `knowledge/cards/CARD-0169-queue-no-idle-compatible-workers.md`.
Реализация уже находится в актуальном `main`; карточка фиксирует её продуктовый
коммит и проверяемый контракт без повторного изменения кода.

ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл internal/controlplane/legacy_poller_import.go
ГОТОВО-КОГДА: файл internal/controlplane/metrics.go
ГОТОВО-КОГДА: файл internal/controlplane/store.go
ГОТОВО-КОГДА: файл internal/controlplane/store_test.go
ГОТОВО-КОГДА: файл internal/controlplane/work_resume_http.go
ГОТОВО-КОГДА: файл internal/controlplane/workflows.go
ГОТОВО-КОГДА: файл internal/controlplane/workflows_test.go
ГОТОВО-КОГДА: файл internal/controlplane/metrics_test.go
ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл internal/worker/attempt_lifecycle.go
ГОТОВО-КОГДА: файл internal/worker/prompt_test.go
ГОТОВО-КОГДА: файл internal/worker/worker_integration_test.go
ГОТОВО-КОГДА: файл migrations/024_queue_reassignment.sql
ГОТОВО-КОГДА: файл migrations/025_queue_reassignment_events.sql
ГОТОВО-КОГДА: файл web/dist/assets/index-Cr57yRzx.js
ГОТОВО-КОГДА: файл web/dist/index.html
ГОТОВО-КОГДА: файл web/src/Overview.test.ts
ГОТОВО-КОГДА: файл web/src/Overview.tsx
ГОТОВО-КОГДА: файл web/src/Workflows.tsx
ГОТОВО-КОГДА: файл web/src/test/fixtures.ts
ГОТОВО-КОГДА: файл web/src/test/setup.ts
ГОТОВО-КОГДА: файл web/src/types.ts
ГОТОВО-КОГДА: команда go test ./internal/controlplane ./internal/worker

# Провалы запусков Automation: видимость и один автоматический повтор

## Цель и влияние на владельца

Владелец на странице Automation видит, что запуск по расписанию не исчез после
сбоя: первый сбой автоматически получает ровно одну попытку повторного запуска,
а интерфейс различает ожидание, выполнение, успешное завершение, окончательный
сбой и причины, по которым повтор не состоялся. Это исключает ручное
расследование обычного transient-сбоя и не создаёт бесконечный цикл запусков.

Работа закрыта как дубликат уже слитой работы #215. Реализация из указанного в
карточке коммита находится в истории `main`; новых продуктовых изменений не
нужно.

## Технический подход и реальные файлы

1. `internal/controlplane/state.go` обрабатывает failure как при обычном
   `CompleteAttempt`, так и при потере lease в `SweepExpired`. Транзакционная
   функция `retryFailedScheduleAutomation` допускает только schedule/run-now
   occurrence с первым failed execution, живым совместимым исходным worker и
   включёнными зависимостями. Она переводит тот же execution в `queued`, ставит
   `retry_count=1` и durable diagnostic; второй сбой получает final status.
2. `internal/controlplane/state.go` в `Claim` удерживает автоматический повтор
   на назначенном исходном worker. Ручные и GitHub-повторы не получают признак
   автоматического повтора.
3. `internal/controlplane/automations.go` читает `retry_count` и переводит
   durable diagnostic в публичный `retry_status`: queued, running, succeeded,
   final_failed, skipped_disabled или skipped_worker_unavailable.
4. `internal/protocol/types.go` добавляет к task summary `retry_count` и
   `retry_status`; `web/src/types.ts` отражает этот API-контракт.
5. `web/src/Automations.tsx` показывает понятную владельцу подпись статуса,
   а `web/src/App.test.tsx` проверяет все пять видимых состояний.
6. `internal/controlplane/schedule_automations_test.go` покрывает lifecycle,
   affinity исходного worker, идемпотентность, eligibility и исключение
   несвязанных задач. `web/src/test/fixtures.ts` и `web/dist/index.html`
   поддерживают тестовые и публикуемые артефакты уже собранного интерфейса.
   Собранный JavaScript обновляется как versioned-hash asset
   `web/dist/assets/index-*.js`.

## Последовательный план

1. Не менять продуктовый код: подтвердить, что implementation commit карточки
   является предком актуального `main`.
2. Синхронизировать CARD-0124: статус Done, работа #215 уже слита, точный
   implementation commit и отсутствие следующего действия.
3. Зафиксировать спецификацию с границами поведения и обязательной целевой
   регрессией для последующих изменений.

## Критерии приёмки

- Первый failed запуск schedule/run-now Automation получает не более одного
  автоматического повтора; второй failed результат виден как окончательный.
- Повтор остаётся у исходного healthy совместимого worker и не может быть
  забран другим worker.
- Отключённая Automation/зависимость либо недоступный worker не создают повтор,
  а дают понятную конечную причину.
- Повторные completion, lease sweep и перезапуск хранилища не создают лишних
  повторов или diagnostic.
- Ручной GitHub retry и обычные задачи не маркируются автоматическим retry.
- Интерфейс показывает queued, running, succeeded, final_failed,
  skipped_disabled и skipped_worker_unavailable человеческими подписями.

## Тест-план

- Обязательная регрессия: `go test ./internal/controlplane -run
  'TestScheduleAutomation(FailedExecutionRetriesOnceAndIsIdempotent|RetryStaysWithOriginalWorker|RetryLifecycleIsExactlyOnce|RetryEligibilityGuardsAreExactlyOnce|RetryExcludesGitHubAndOrdinaryTasks)' -count=1`.
- UI-регрессия: `cd web && npm test -- --run web/src/App.test.tsx` проверяет
  пять пользовательских статусов повтора.
- Для изменения жизненного цикла дополнительно проверить ветки
  `CompleteAttempt` и `SweepExpired`, cancellation и перезапуск SQLite.

## Риски и решения

| Риск | Решение |
| --- | --- |
| Бесконечный retry расходует worker capacity | Durable `retry_count=1` и final diagnostic после второго failure. |
| Повтор уходит другому worker | Claim разрешает retry только назначенному исходному worker. |
| Скрытый failure выглядит успешным | API передаёт retry_status, UI выводит отдельные подписи конечных причин. |
| Ручной retry ошибочно выглядит автоматическим | Статус задаётся только durable diagnostic автоматического schedule retry. |
| Повторные сигналы создают дубликаты | CAS-условия execution state/retry count и lifecycle-тест exactly-once. |

## Карточка работы

Карточка: `knowledge/cards/CARD-0124-automation-failure-visibility-and-single-retry.md`.

Статус: Done, дубликат слитой работы #215. Текущая документация фиксирует
реальную поставку без повторного изменения продукта.

ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл internal/controlplane/automations.go
ГОТОВО-КОГДА: файл internal/controlplane/schedule_automations_test.go
ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл web/src/Automations.tsx
ГОТОВО-КОГДА: файл web/src/App.test.tsx
ГОТОВО-КОГДА: файл web/src/types.ts
ГОТОВО-КОГДА: файл web/src/test/fixtures.ts
ГОТОВО-КОГДА: файл web/dist/index.html
ГОТОВО-КОГДА: файл web/dist/assets/index-4UunqATt.js
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run 'TestScheduleAutomation(FailedExecutionRetriesOnceAndIsIdempotent|RetryStaysWithOriginalWorker|RetryLifecycleIsExactlyOnce|RetryEligibilityGuardsAreExactlyOnce|RetryExcludesGitHubAndOrdinaryTasks)' -count=1

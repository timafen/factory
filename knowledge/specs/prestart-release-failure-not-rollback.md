# Приёмка 06: отказ до изменения сервера — это `failed`

## Цель и влияние на владельца

Владелец должен видеть правдивый исход выпуска: определённый отказ broker до
запуска операции и невозможность стартовать release executable означают обычный
неуспешный выпуск (`failed`), а не неудачный откат. `rollback_failed` должен
сообщать только о ситуации, где откат требовался, но его восстановление не
подтверждено. Это устраняет ложное сообщение о повреждённом состоянии сервера и
даёт владельцу понятное действие: исправить причину отказа и повторить выпуск.

## Технический подход и реальные файлы

- В `internal/controlplane/project_adapters.go` обработать definitive 4xx/POST
  отказ broker как durable `failed` с сообщением о том, что broker отклонил
  операцию до старта; неизвестный результат POST по-прежнему оставить running
  для последующего poll.
- В `internal/releasebroker/broker.go` вернуть `failed`, если executable не
  удалось запустить. Ошибка после фактического старта должна сохранить текущую
  семантику: успешный выпуск, `release_failed_rolled_back`, либо
  `rollback_failed` по результату rollback.
- В `internal/controlplane/project_adapters.go` расширить разбор durable-статуса
  broker значением `failed`; не менять смысл `release_failed_rolled_back`,
  `health_failed_rolled_back` и `rollback_failed`.
- В `migrations/021_projects.sql` добавить `failed` в CHECK для новых баз и
  подготовить совместимое обновление существующей схемы, если миграционный
  механизм проекта этого требует.
- В `web/src/types.ts` добавить `failed` в `ProjectOperation.status` и проверить
  `web/src/Projects.tsx`/форматирование сообщения: UI не должен превращать его
  в rollback failure.
- Тесты: `internal/controlplane/project_adapters_test.go`,
  `internal/releasebroker/broker_test.go`, `web/src/Projects.test.tsx` и при
  необходимости API/миграционные тесты в соответствующих пакетах.

## Последовательный план

1. Добавить durable-статус `failed` в схему, серверный разбор и TypeScript-контракт.
2. Разделить pre-start ошибки broker и executor от ошибок, возникших после
   старта процесса или во время требуемого rollback.
3. Закрепить сообщения: отказ broker явно говорит «до старта», а невозможность
   запуска executable не заявляет о rollback.
4. Обновить/добавить регрессионные тесты control plane, releasebroker и Projects.
5. Проверить сохранение семантики трёх rollback-статусов и неизвестного POST.

## Критерии приёмки

- POST broker с определённым отказом (4xx) для release завершается durable
  `failed`, не `rollback_failed`, с сообщением о pre-start rejection.
- Невозможность `command.Start()` для release executable завершается durable
  `failed` и не оставляет operation running.
- `release_failed_rolled_back` остаётся только для подтверждённого автоматического
  rollback после ошибки выпуска.
- `health_failed_rolled_back` и `rollback_failed` сохраняют существующее
  значение; последний используется только когда требуемое восстановление не
  подтверждено.
- Неопределённый результат POST не классифицируется как failed: операция
  остаётся наблюдаемой до poll, согласно текущему safety-контракту.
- API, durable store и TypeScript принимают `failed`; Projects показывает
  владельцу честное сообщение без слова/смысла «неудачный откат».

## Тест-план

- `go test ./internal/controlplane -run 'TestBrokerDefinitiveRejectionDoesNotLeaveOperationRunning|TestTarserNeverClaimsAnUnverifiedRollback|TestFactoryAutomaticRollbackRequiresRestoredHealth' -count=1`;
  первый тест должен быть изменён на ожидание `failed` и сообщение pre-start.
- Добавить тест executor для ошибки `Start()` и запустить
  `go test ./internal/releasebroker -count=1`.
- Запустить целевые Projects-тесты в `web` (включая новый сценарий `failed`) и
  TypeScript-проверку проекта.
- Проверить миграцию на чистой БД и чтение всех старых rollback-статусов.

## Риски и решения

- Риск: `failed` отвергнет старый CHECK или потребитель контракта. Решение:
  обновить миграцию, Go-разбор и TypeScript одновременно, затем пройти API/UI.
- Риск: ошибка POST может быть неопределённой. Решение: менять только
  `projectBrokerDefinitelyRejected`; unknown оставлять running.
- Риск: слишком широкая замена `rollback_failed` скроет реальный rollback.
  Решение: тестами зафиксировать restored-health и exact broker outcomes.
- Риск: процесс успел начаться, хотя `Start` вернул ошибку, ограничен
  границей executor; durable классификация должна отражать только отсутствие
  подтверждённого запуска и не объявлять rollback.

## Карточка работы

Карточка: `knowledge/cards/CARD-0302-prestart-release-failure-not-rollback.md`.
Область ограничена контрактом статусов, классификацией pre-start ошибок,
регрессиями и отображением результата; реальный выпуск и rollback-скрипты вне
объёма.

ГОТОВО-КОГДА: файл internal/controlplane/project_adapters.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker.go
ГОТОВО-КОГДА: файл migrations/021_projects.sql
ГОТОВО-КОГДА: файл web/src/types.ts
ГОТОВО-КОГДА: файл web/src/Projects.tsx
ГОТОВО-КОГДА: файл internal/controlplane/project_adapters_test.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker_test.go
ГОТОВО-КОГДА: файл web/src/Projects.test.tsx
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run 'TestBrokerDefinitiveRejectionDoesNotLeaveOperationRunning|TestTarserNeverClaimsAnUnverifiedRollback|TestFactoryAutomaticRollbackRequiresRestoredHealth' -count=1

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
  отказ broker в `RunProjectOperation` как durable `failed` с сообщением о том,
  что broker отклонил операцию до старта; неизвестный результат POST по-прежнему
  оставить `running` для последующего poll. В `parseProjectReleaseBrokerStatus`
  принять terminal-значение `failed`, а в `ProjectOperation` завершать его без
  health-check и без запуска rollback.
- В `internal/releasebroker/broker.go` вернуть `failed`, если executable не
  удалось запустить. Ошибка после фактического старта должна сохранить текущую
  семантику: успешный выпуск, `release_failed_rolled_back`, либо
  `rollback_failed` по результату rollback.
- В `internal/controlplane/project_adapters.go` расширить разбор durable-статуса
  broker значением `failed`; не менять смысл `release_failed_rolled_back`,
  `health_failed_rolled_back` и `rollback_failed`.
- В `migrations/031_project_operation_failed_status.sql` пересоздать SQLite
  таблицу `project_operations` с расширенным CHECK, скопировать данные и
  восстановить частичный уникальный индекс. `021_projects.sql` уже применена
  существующими базами, поэтому её изменение не обновит их схему; новая миграция
  одновременно будет применена и к чистой базе после `021`.
- В `web/src/types.ts` добавить `failed` в `ProjectOperation.status` и проверить
  `web/src/Projects.tsx`/форматирование сообщения: UI не должен превращать его
  в rollback failure.
- Тесты: `internal/controlplane/project_adapters_test.go`,
  `internal/releasebroker/broker_test.go`, `web/src/Projects.test.tsx` и при
  необходимости API/миграционные тесты в соответствующих пакетах.

## Последовательный план

1. Добавить новую миграцию для durable-статуса `failed`, серверный разбор и
   TypeScript-контракт.
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
- Когда broker уже вернул terminal `failed`, повторный poll сохраняет этот
  статус и не выполняет health-check либо rollback как побочный эффект.

## Тест-план

- Изменить `TestBrokerDefinitiveRejectionDoesNotLeaveOperationRunning`: 409 на
  POST должен дать `failed`, а сообщение должно содержать «до старта»; добавить
  в `TestFactoryBrokerReportsExactAutomaticRollbackOutcomes` terminal `failed`
  и проверку отсутствия health/rollback.
- Добавить `TestFXExecutorStartFailureIsFailed`: несуществующий executable
  возвращает `failed`, а не `rollback_failed`.
- Запустить обязательную команду из блока «ГОТОВО-КОГДА»; она одновременно
  проверяет pre-start 4xx, ошибку `Start()` и сохранение настоящих rollback
  исходов.
- Запустить целевые Projects-тесты в `web` (включая новый сценарий `failed`) и
  TypeScript-проверку проекта.
- Проверить миграцию на чистой БД и чтение всех старых rollback-статусов.

## Риски и решения

- Риск: `failed` отвергнет старый CHECK существующей SQLite-базы или потребитель
  контракта. Решение: добавить новую миграцию (не переписывать применённую 021),
  затем обновить Go-разбор и TypeScript одновременно и пройти API/UI.
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
ГОТОВО-КОГДА: файл migrations/031_project_operation_failed_status.sql
ГОТОВО-КОГДА: файл web/src/types.ts
ГОТОВО-КОГДА: файл web/src/Projects.tsx
ГОТОВО-КОГДА: файл internal/controlplane/project_adapters_test.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker_test.go
ГОТОВО-КОГДА: файл web/src/Projects.test.tsx
ГОТОВО-КОГДА: команда go test ./internal/controlplane ./internal/releasebroker -run 'TestBrokerDefinitiveRejectionDoesNotLeaveOperationRunning|TestFXExecutorStartFailureIsFailed|TestFactoryBrokerReportsExactAutomaticRollbackOutcomes' -count=1

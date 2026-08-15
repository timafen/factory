# Предзапусковой сбой выпуска не является неудачным откатом

## Цель и влияние на владельца

Владелец должен видеть правдивый terminal status: если release-driver не удалось
запустить, сервер ещё не изменялся и отката не было, поэтому операция должна
завершаться как `failed`. Это отделяет неисправный путь запуска от
`rollback_failed`, который означает, что после изменения/попытки операции
восстановление не подтверждено. Неопределённый результат POST broker по-прежнему
остаётся `running` до опроса и не классифицируется как отказ запуска.

## Технический подход и реальные файлы

- `internal/releasebroker/broker.go`: в `FXExecutor.ExecuteDeliveryWithPID`
  вернуть `failed` при ошибке `command.Start()`; сохранить `failed` для
  невалидной invocation и остановки после callback, `release_failed_rolled_back`
  для exit code 6 и `rollback_failed` для результата после запуска без
  подтверждённого отката.
- `internal/releasebroker/broker_test.go`: добавить regression на
  отсутствующий/неисполняемый release-driver и проверить terminal `failed`, а
  также сохранить проверки exit code 6 и существующих rollback-исходов.
- `internal/controlplane/project_adapters.go`: принять broker outcome `failed`
  и завершить project operation `failed` без health-check и без запуска rollback;
  не менять ветку неизвестного/неопределённого broker POST.
- `internal/controlplane/project_adapters_test.go`: проверить mapping `failed`,
  отсутствие вызовов health/rollback, сохранение `rollback_failed` для
  подтверждённо неуспешного восстановления и сохранение `running` для unknown
  POST.
- `web/src/types.ts`: добавить `failed` в union статусов `ProjectOperation`.
- `migrations/021_projects.sql`: добавить `failed` в CHECK constraint, чтобы
  terminal status API и durable storage имели одинаковый контракт.
- `pilot/pilot.py` и `pilot/test_pilot.py`: проверить/обновить потребление
  terminal `failed`, если текущий status-dispatch не принимает его; добавить
  regression только при подтверждённой необходимости.

## Последовательный план

1. Написать broker regression с driver path, который нельзя запустить, и
   зафиксировать отсутствие запуска/мутации.
2. Изменить только классификацию ошибки `Start`; не менять shell-откат и код
   exit 6.
3. Провести `failed` через durable broker status и control-plane reconciliation.
4. Завершать project operation `failed` напрямую, без health-check и rollback.
5. Синхронизировать TypeScript и SQL-контракты, затем проверить Pilot.

## Критерии приёмки

1. Несуществующий или неисполняемый release-driver возвращает `failed`.
2. Driver, завершившийся кодом 6 для release adapter, возвращает
   `release_failed_rolled_back`.
3. Project operation с broker `failed` становится `failed`; health checker и
   rollback runner не вызываются.
4. `rollback_failed` сохраняется для не подтверждённого восстановления, а не
   для отказа `command.Start()`.
5. Unknown/неопределённый результат POST остаётся `running` до опроса.
6. API TypeScript и SQL принимают `failed`; прежние terminal statuses не
   меняют смысл.

## Тест-план

- `go test ./internal/releasebroker ./internal/controlplane`
- `npx tsc -p web/tsconfig.app.json --noEmit`
- `python3 -m unittest pilot.test_pilot` (или целевой regression, если полный
  модуль не требуется изменениями).
- Обязательный новый тест: broker Start failure → `failed` и control-plane
  `failed` без health/rollback.
- Проверить `git diff --check` и отсутствие изменений UI/продуктовой логики,
  не относящихся к перечисленному контракту.

## Риски и решения

- Ошибка транспортного POST может быть неизвестной: не трактовать её как
  `failed`, оставлять `running` и полагаться на durable polling.
- Дублирование `failed` в Go/SQL/TS может разойтись: обновить все перечисленные
  контракты и покрыть round-trip тестом.
- Слишком широкое переименование rollback-ошибок исказит диагностику: менять
  только pre-start `command.Start`, не shell-логику и не подтверждённый
  `rollback_failed`.

## Карточка работы

`knowledge/cards/CARD-0302-prelaunch-release-failure-not-rollback-failed.md`

ГОТОВО-КОГДА: файл internal/releasebroker/broker.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker_test.go
ГОТОВО-КОГДА: файл internal/controlplane/project_adapters.go
ГОТОВО-КОГДА: файл internal/controlplane/project_adapters_test.go
ГОТОВО-КОГДА: файл web/src/types.ts
ГОТОВО-КОГДА: файл migrations/021_projects.sql
ГОТОВО-КОГДА: команда go test ./internal/releasebroker ./internal/controlplane


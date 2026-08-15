# CARD-0302: Предзапусковой сбой выпуска

Implementation commit: pending — этап Specification не изменяет продуктовый код.

## Контекст

`FXExecutor.ExecuteDeliveryWithPID` уже возвращает `failed`, когда invocation
невалиден, но ошибка `command.Start()` сейчас получает `rollback_failed`, хотя
release-driver не запускался. Control plane и TypeScript-контракт также должны
проводить `failed` как отдельный terminal status.

## Результат

Предзапусковой отказ виден владельцу как `failed` без health-check и rollback;
автоматический rollback с кодом 6 остаётся `release_failed_rolled_back`, а
неопределённый POST остаётся `running` до опроса.

## Scope реализации

- `internal/releasebroker/broker.go`
- `internal/releasebroker/broker_test.go`
- `internal/controlplane/project_adapters.go`
- `internal/controlplane/project_adapters_test.go`
- `web/src/types.ts`
- `migrations/021_projects.sql`
- `pilot/pilot.py` и `pilot/test_pilot.py` — только если проверка выявит
  несовместимость потребителя статуса.

## Обязательное доказательство

`go test ./internal/releasebroker ./internal/controlplane` завершается кодом 0;
новый regression доказывает `failed` до изменения сервера и отсутствие rollback.

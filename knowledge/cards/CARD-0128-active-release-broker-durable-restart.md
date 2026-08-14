# CARD-0128 — Active release broker: durable restart

Implementation commit: 33a59878c22519eb65f5c5eaa472f53531014967 — текущий базовый снимок, на котором зафиксирован контракт release broker для этой спецификации

- Status: Specification — ожидает реализации/проверки.
- Scope: заменить active broker и перезапустить `factory-release-broker.service`
  только после durable-success; не менять UI.
- Owner outcome: установленный broker обслуживает следующий запрос, а уже
  принятый terminal result переживает restart без повторного выпуска.
- Planned implementation: `cmd/factory-release-broker/main.go`,
  `internal/releasebroker/broker.go`, `internal/releasebroker/broker_test.go`,
  `ops/install-project-release-broker.sh`, `ops/systemd/factory-release-broker.service`,
  `ops/fx-factory-release`, `ops/test-install-project-release-broker.sh`.
- Acceptance proof: Go durable/restart tests плюс installer fixture; обязательная
  команда указана в `knowledge/specs/active-release-broker-replacement-and-durable-restart.md`.
- Next action: реализация должна сохранить fail-closed recovery и active/inactive
  systemd порядок, затем передать результат на Verify.

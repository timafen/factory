# CARD-0045 — Перенос патруля Claude в Factory Automations

## HEAD

- Status: Ready for Review — замечания по версии и размеру контекста исправлены.
- Branch: `factory/a16a4ddc-029-01696424-114`.
- Head commit: `702130a` — атомарная защита конфигурации патруля.
- What changed: первое provision добавляет инструкции и увеличивает версию Automation через CAS; повторный вызов не меняет версию. Контекст свыше 8 KiB отклоняется до записи.
- Evidence: `go test ./internal/controlplane -run 'Test.*(Schedule|Patrol)'` → PASS; `go vet ./internal/controlplane` и `go build ./...` → PASS; UI typecheck/build и 63 компонентных теста → PASS; 87 тестов пилота → PASS.
- One next action: повторно проверить ветку на Review.

## LOG

### 2026-08-10 — Specification

Владелец определил источник задания: не внешний Claude-патруль, а уже
существующий встроенный пробный патруль. Спецификация переносит его смысл,
не угадывает отсутствующие cron, часовой пояс или дополнительные проверки.

### 2026-08-10 — Implement

Provisioner использует существующую schedule Automation, сохраняет в ней
инструкции патруля и не меняет cron или timezone. Повторный provision не
дублирует контекст, а due-run сохраняется как Occurrence с привязанной Task.
Целевые Go и Python проверки завершились успешно.

### 2026-08-10 — Implement

Добавлен продуктовый provision по явному Automation ID и действие с
подтверждением в панели schedule Automation. Интеграционный тест включает
патруль через HTTP и проводит due schedule через durable Occurrence до Task;
целевые и полные Go/UI/Python проверки, vet и сборка завершились успешно.

### 2026-08-10 — Implement

Первое добавление инструкций патруля теперь атомарно увеличивает версию
Automation через CAS, поэтому устаревшее редактирование после отключения не
может стереть инструкции. Повторный provision сохраняет версию, а итоговый
контекст проверяется на границе 8 KiB до записи. Целевые Go-тесты, сборка,
Go vet, UI typecheck/build и профильные UI/Python тесты завершились успешно.

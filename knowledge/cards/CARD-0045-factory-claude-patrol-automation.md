# CARD-0045 — Перенос патруля Claude в Factory Automations

## HEAD

- Status: Ready for Review — блокирующий путь provision восстановлен и проверен.
- Branch: `factory/9efaf5bb-9b4-d38e9946-bd5`.
- Head commit: `1e44f27` — включение патруля через HTTP и панель Automations.
- What changed: schedule Automation с явным ID получает durable инструкции патруля через HTTP или подтверждение в панели; runtime пробуждается после provision. Сквозная проверка доводит наступившее расписание до одной Occurrence и связанной Task.
- Evidence: `go test ./internal/controlplane -run 'Test.*(Schedule|Patrol)'` → PASS; `npm test -- --run src/App.test.tsx` → PASS; `go test -timeout 5m ./...`, UI build/lint/typecheck/tests, `go vet ./...`, сборка бинарников и `python3 -m unittest pilot.test_pilot` → PASS.
- One next action: принять Review после проверки provision из `/automations/<id>` на существующем schedule.

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

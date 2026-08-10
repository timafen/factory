# CARD-0045 — Перенос патруля Claude в Factory Automations

## HEAD

- Status: Implemented — проверка запуска Automation выполнена.
- Branch: `factory/850c1e5e-d5e-17f49600-f1f`.
- Head commit: `e4ee5bc` — перенос патруля в расписание Automation.
- What changed: существующая schedule Automation получает durable инструкции патруля и включается без создания второго расписания; `pilot` больше не запускает legacy patrol в цикле.
- Evidence: `go test ./internal/controlplane -run 'Test.*(Schedule|Patrol)'` → PASS; `python3 -m unittest pilot.test_pilot` → PASS.
- One next action: проверить provisioner на runtime Automation с реальным существующим расписанием.

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

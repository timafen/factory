# CARD-0045 — Перенос патруля Claude в Factory Automations

## HEAD

- Status: Specified — ожидает согласования перед реализацией.
- Branch: `factory/bca3cfc3-f2b-15eaaedf-a5c`.
- Specification: `knowledge/specs/factory-claude-patrol-automation.md`.
- What changes: существующий пробный патруль конвейера станет scheduled Automation; каждый запуск и его Task останутся в истории Automations.
- Evidence: спецификация сверена с `pilot/pilot.py`, schedule runtime и существующей моделью Occurrence; область реализации и целевая проверка закреплены строками `ГОТОВО-КОГДА`.
- One next action: согласовать способ однократного создания Automation из уже имеющихся workflow и расписания.

## LOG

### 2026-08-10 — Specification

Владелец определил источник задания: не внешний Claude-патруль, а уже
существующий встроенный пробный патруль. Спецификация переносит его смысл,
не угадывает отсутствующие cron, часовой пояс или дополнительные проверки.

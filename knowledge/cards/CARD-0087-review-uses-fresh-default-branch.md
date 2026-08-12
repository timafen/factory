# CARD-0087: Review и Verify используют свежую основную ветку

## HEAD

Status: implemented; Pilot/live Workflow revisions remain unchanged.
Branch: `factory/0b933443-daf-3aa76b07-abe`.
Implementation commit: 80e51dc165b6dc3f9732c8aacb35a0fcefc097a5 — из примера Pilot убраны неподдерживаемые метаданные rollout.
What changed: `pilot/config.example.json` теперь содержит только поля серверной схемы; план rollout остаётся в карточке, а не в runtime-конфигурации.
Evidence: `umask 077; go test ./internal/controlplane -run '^TestPilotConfigExampleMatchesServerSchema$' -count=1` → PASS.
Evidence: `umask 077; go test ./...`, `python3 -m unittest pilot.test_pilot`, JSON validation, `go build ./cmd/factory-server` и `git diff --check` → PASS.
Next action: создать и проверить новые immutable-ревизии Review/Verify перед их закреплением в live Pilot config.

## LOG

### 2026-08-11 — Specification

Статус: specification

Результат: Review/Verify перед сравнением получают authoritative default branch
из remote, обновляют именно этот ref и фиксируют base/candidate SHA. При сбое
получения задача становится BLOCKED. Existing running tasks не изменяются.

Связь: worker-discovered finding из CARD-0085; CARD-0086 зарезервирована.

### Передача в реализацию

- Спецификация: `knowledge/specs/review-fresh-default-branch.md`.
- Реализатор меняет только перечисленные там runtime/test/config files и не
  редактирует эту карточку без добавления доказательства результата.
- Live Pilot получает новые ревизии Review и Verify безопасным добавлением
  immutable revisions; новые задачи и Pilot выбирают исправленные ревизии.
- Rollback: переключить Pilot/config обратно на предыдущие revision_id; уже
  созданные task snapshots и running tasks не мутировать.

### 2026-08-11 — Implement

Исправлена ложная блокировка: кандидат от прежнего main сравнивается со свежим
main через их pinned общий merge-base. Продвижение базы описывается в Review,
а не переводит проверку в инфраструктурный BLOCKED.

Регрессия использует реальный bare remote и не зависит от cached refs; полный
`python3 -m unittest pilot.test_pilot` проходит: 202 tests OK. Также PASS:
`go test ./...`, `go build ./cmd/factory-server`, JSON config и `git diff --check`.

### 2026-08-11 — Implement

Из `pilot/config.example.json` удалены метаданные rollout Review/Verify,
которые не являются настройкой сервера и отклонялись строгим декодером.
Проверки PASS при `umask 077`: focused schema test, `go test ./...`,
`python3 -m unittest pilot.test_pilot`, JSON validation, build и diff check.

# CARD-0087: Review и Verify используют свежую основную ветку

## HEAD

Status: implemented; Pilot/live Workflow revisions remain unchanged.
Branch: `factory/ccb67bbc-aa2-1984ff28-05f`.
Implementation commit: ff076ae565626fec8a3150414307e2c66d231b11 — Review сохраняет проверку кандидата после продвижения main.
What changed: fresh isolated snapshot pins default-base, candidate and their shared merge-base; scope is calculated only as pinned `merge_base_sha...candidate_sha`.
What changed: default-branch advancement is explicit context, not BLOCKED; missing or unrelated history and resolution/fetch failures remain BLOCKED. Legacy `branch_report` remains an injectable compatibility seam.
Evidence: `python3 -m unittest pilot.test_pilot` → PASS (202 tests); bare-remote regression covers an old-main candidate after remote main advances.
Evidence: `go test ./...`, `go build ./cmd/factory-server`, JSON config validation and `git diff --check` → PASS.
Next action: create and smoke new immutable Review/Verify revisions, then pin their IDs in live Pilot config.

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

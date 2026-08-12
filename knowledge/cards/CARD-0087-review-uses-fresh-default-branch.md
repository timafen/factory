# CARD-0087: Review и Verify используют свежую основную ветку

## HEAD

Status: Implemented — ready for Verify.
Branch: `factory/1afd7d9f-72c-facc4b8f-b73`.
Implementation commit: ac3ef660715a20f7b50711a57f7d787f63883598 — Review получает свежий pinned snapshot remote default branch.
What changed: immutable Revision 10 for Review (`cce09cec-256d-41c4-83fc-a7c58150cef4`) and Verify (`e2bc55e2-c288-4970-8424-316195217732`) now require remote-HEAD resolution, isolated fetch, pinned base/candidate SHA, and infrastructure BLOCKED verdicts.
What changed: Pilot dynamically reads these current revision IDs; existing task snapshots were not changed.
Evidence: `python3 -m unittest pilot.test_pilot -q` → PASS (225 tests, 13 skipped); live API smoke confirms both Revision 10 instructions and Pilot selection.
Next action: Verify this published branch against freshly resolved remote `main`.

## LOG

### 2026-08-12 — Implement

Поставка перебазирована на свежий `origin/main`; реализация остаётся связана с
кодовым коммитом `ac3ef660715a20f7b50711a57f7d787f63883598`, а отдельный
commit карточки фиксирует актуальную ветку. Полный `python3 -m unittest
pilot.test_pilot -q` прошёл: 225 tests OK, 13 skipped.

### 2026-08-12 — Implement

Исправлены три устаревших точки совместимости Pilot: полный `python3 -m unittest
pilot.test_pilot -q` проходит. В live control plane созданы immutable Revision 10
для Review и Verify: обе закрепляют remote default/candidate SHA до сравнения и
отдают BLOCKED при ошибке инфраструктуры. Smoke через API подтвердил, что Pilot
видит новые текущие ревизии; существующие task snapshots не изменялись.

### 2026-08-11 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Свежая база и точный scope | `python3 -m unittest pilot.test_pilot` | PASS: real bare-remote fixture показывает stale scope из 12 файлов и pinned scope из 11 файлов, `ahead_by=2`, SHA и сохранение ветки воркера. |
| Инфраструктурный сбой не обвиняет код | тот же набор, `FreshDefaultBranchSnapshotTests` | PASS: failure resolution/fetch даёт BLOCKED без REQUEST CHANGES. |
| Полный Pilot-набор | `python3 -m unittest pilot.test_pilot -q` | BLOCKED: 202 tests, 3 errors — два `CardNumberReservationTests` получают blocked result вместо старого `back`, а `SpecificationBranchHandoffTests` ожидает прежний `branch_report`/gh seam. |
| Регрессии runtime | `go test ./...`; `go build ./cmd/factory-server` | PASS. |
| Регрессии web | `npm run typecheck`; `npm test` | PASS: 14 файлов тестов, 155 тестов. |
| Чистота поставки | `git diff --check`; `git diff --name-only origin/main...HEAD` | PASS: только запись Verify в карточке. |
| Live rollout | проверка `## HEAD` и rollout-плана карточки | BLOCKED: immutable revisions не созданы и не закреплены; это обязательный критерий приёмки. |

### 2026-08-11 — Specification

Статус: specification

Результат: Review/Verify перед сравнением получают authoritative default branch
из remote, обновляют именно этот ref и фиксируют base/candidate SHA. При сбое
получения задача становится BLOCKED. Existing running tasks не изменяются.

Связь: worker-discovered finding из CARD-0085; CARD-0086 зарезервирована.

### 2026-08-11 — Implement

Реализован isolated fetch-and-pin snapshot для Review и блокировка инфраструктурных ошибок без cached `origin/main`.
Регрессия с bare remote доказывает: stale comparison даёт 12 файлов, pinned snapshot — точные 11 и `ahead_by=2`; ветка воркера сохраняется.
Проверены `python3 -m unittest pilot.test_pilot`, `go test ./...`, `go build ./cmd/factory-server`, JSON config и `git diff --check` — PASS.

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

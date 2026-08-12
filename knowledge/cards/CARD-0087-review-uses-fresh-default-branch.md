# CARD-0087: Review и Verify используют свежую основную ветку

## HEAD

Status: implemented and tested; ready for Review.
Branch: `factory/691ad2ed-938-eabe701c-71b`.
Implementation commit: 6f47f35b1ef6261a47c4a01f75c27363efda75b8 — закреплена граница между продвижением main и несвязанной историей кандидата.
What changed: свежий `main` уже содержит merge-base/three-dot исправление и восстановленный legacy `branch_report`; добавлена bare-remote регрессия, что только отсутствие общей истории остаётся infrastructure BLOCKED.
Evidence: `python3 -m unittest pilot.test_pilot` → PASS, 203 tests; focused Review seams/snapshots → PASS, 8 tests.
Evidence: targeted retry двух resource-sensitive worker tests, `go build ./cmd/factory-server`, py_compile, JSON validation и `git diff --check` → PASS.
Evidence: первый `go test ./...` → FAIL только в двух `internal/worker` timeout-тестах вне scope при высокой параллельной нагрузке; оба отдельно → PASS.
Next action: Review confirms the two original findings stay fixed on fresh `origin/main` and accepts the one-file regression scope.

## LOG

### 2026-08-11 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Пример Pilot проходит строгую серверную схему | `umask 077; go test ./internal/controlplane -run '^TestPilotConfigExampleMatchesServerSchema$' -count=1` | PASS: пример декодирован строгим `PilotConfigStore`; `respect_host_load=true`, `max_parallel_works=4`. |
| Полная Go-регрессия чиста | `umask 077; go test ./...` | PASS: все пакеты прошли. |
| Поведение Pilot и свежих Review/Verify не нарушено | `python3 -m unittest pilot.test_pilot`; `python3 -m unittest pilot.test_pilot.FreshDefaultBranchSnapshotTests` | PASS: 202 tests OK; focused 3 tests OK. |
| JSON, сборка и чистота diff | `python3 -m json.tool pilot/config.example.json`; `go build ./cmd/factory-server`; `git diff --check` | PASS. |
| Scope и поставка согласованы | `git diff --name-only origin/main...HEAD`; `git rev-list --left-right --count origin/main...HEAD`; проверка отсутствия `rollout` | PASS: только CARD-0087 и пример; behind_by=0; поле `rollout` отсутствует. |
| Реализационный коммит корректен | `git merge-base --is-ancestor 80e51dc165b6dc3f9732c8aacb35a0fcefc097a5 HEAD` | PASS: SHA — предок ветки и меняет runtime-файл вне `knowledge/cards/`. |

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

### 2026-08-11 — Implement

После rebase подтверждено, что runtime-исправление `ff076ae` уже находится в
свежем `main`: Review pin-ит общий merge-base и использует three-dot scope, а
`branch_report` сохраняет legacy seam. Добавлена bare-remote регрессия для
несвязанных историй, чтобы ослабление infrastructure BLOCKED не прошло незаметно.

`python3 -m unittest pilot.test_pilot` → PASS, 203 tests; focused 8 tests,
повтор двух упавших из-за общей нагрузки `internal/worker` timeout-тестов,
сборка, py_compile, JSON и diff check → PASS. Полный Go-прогон имел только эти
два внешних timeout-сбоя вне изменённого scope.

# CARD-0087: Review и Verify используют свежую основную ветку

## HEAD

Status: Verified PASS — awaiting human merge.
Branch: `factory/328299ee-9b7-dc24fba0-d5c`.
Implementation commit: 80e51dc165b6dc3f9732c8aacb35a0fcefc097a5 — из примера Pilot убраны неподдерживаемые метаданные rollout.
What changed: `pilot/config.example.json` теперь содержит только поля серверной схемы; план rollout остаётся в карточке, а не в runtime-конфигурации.
Evidence: pinned base `35320922ba648844634816442028be3ca03835e5`, candidate `b1264d9d4724e64eea69549b9e2c04b45d94f475`; реализационный коммит — предок обоих. Функциональная правка уже в `main`, а в candidate до этой записи только карточка.
Evidence: JSON validation, строгая серверная схема, `go test ./...`, 226 Pilot-тестов, TypeScript, web lint и web tests → PASS.
Next action: человек подтверждает merge документационной записи Verify.

## LOG

### 2026-08-12 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Неподдерживаемое поле удалено и пример принимается сервером | `python3 -m json.tool pilot/config.example.json`; `go test ./internal/controlplane -run '^TestPilotConfigExampleMatchesServerSchema$' -count=1` | PASS: JSON валиден, строгая серверная схема принимает пример; `rollout` отсутствует. |
| Полная регрессия | `go test ./...`; `python3 -m unittest pilot.test_pilot` | PASS: все Go-пакеты; 226 тестов Pilot OK (13 skipped). |
| Web-регрессия | `cd web && npx tsc -p tsconfig.app.json --noEmit`; `npm run lint`; `npm test` | PASS. |
| Поставка и реализационный коммит согласованы | pinned `35320922ba648844634816442028be3ca03835e5...b1264d9d4724e64eea69549b9e2c04b45d94f475`; `merge-base --is-ancestor 80e51dc165b6dc3f9732c8aacb35a0fcefc097a5` | PASS: code commit меняет `pilot/config.example.json`, уже входит в base; candidate содержит только эту карточку. |

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

### 2026-08-12 — Implement

По решению владельца задача закрыта как уже выполненная: реализационный коммит
`80e51dc165b6dc3f9732c8aacb35a0fcefc097a5` входит в свежий `origin/main`
через PR #135, а до этой записи трёхточечный diff был пуст. Повторный Verify не
запускался; целевая проверка строгой схемы и JSON validation прошли.

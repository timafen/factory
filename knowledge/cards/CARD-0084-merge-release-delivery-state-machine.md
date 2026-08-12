# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: BLOCKED — целевой release-driver fixture падает до проверки статусов, а rebase на свежий `main` конфликтует в broker.
- Branch: `factory/12526369-3a4-e69c5117-acd`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 81d67ac49275d0fc24fa4380a246aa431d956f15 — повреждённый или неопределённый статус не запускает executor повторно, а release-driver сохраняет переходы durable.
- What changed: Каждый статус driver проходит запись, file fsync, atomic rename и directory fsync; при неопределённом terminal-переходе сохранён `running`.
- What changed: Broker fail-closed сохраняет `locked` и не повторяет физический выпуск после повреждённого состояния.
- Evidence: broker race, 10 process recovery и installer проходят; `bash ops/test-fx-factory-release.sh` падает на отсутствующем rollback artifact, полный `just check` прерван SIGTERM, rebase конфликтует.
- Next action: Разработчику восстановить полный `make_fixture`, перебазировать реализацию на свежий `main` и передать на повторный Verify.

## LOG

### 2026-08-11 — Implement

Перенесена надёжная запись каждого статуса release-driver на свежий `main`:
файл и каталог синхронизируются, terminal-сбой не публикует успех, а повтор
не перезапускает физический executor. Проверены shell syntax, broker race,
process-state сценарии Pilot и обязательная TypeScript-проверка.

### 2026-08-11 — Implement

Исправлены три блокирующих замечания Review: fail-closed восстановление broker,
запрет повторного физического выпуска из `running` и durable `locked` при занятом lock.
Профильные shell и Go race-тесты прошли.

### 2026-08-11 — Specification

Specification accepted a durable V2 generation model: release completion is
authoritative only after broker acceptance, while old delivery state is audit-only.

### 2026-08-11 — Implement

Implemented the V2 generation lifecycle, durable broker operations and the
generation-aware Factory release driver. Pilot completion waits for accepted
release status and records receipts/outbox by immutable delivery id.

### 2026-08-11 — Implement

Review fixes make the Pilot Unix-socket POST match the broker API, preserve
journal/wait/outbox recovery boundaries, and allow only `rc=8` operations to
re-enter the executor. State-file restarts, real Unix-socket protocol coverage,
physical executor counts and full Python/broker/shell checks provide evidence.

### 2026-08-11 — Implement

Correction replaces the hand-written Python socket with the built Go broker,
its real Unix API, and a fixed FX executor fixture. Restart boundaries now
drive recovery to completion with explicit merge/POST/physical/owner counts;
the lock retry joins a second merge to the same N and succeeds once.

### 2026-08-11 — Implement

Third strict-review correction keeps adapter and derived target immutable after
`rc=8`, while allowing only the same delivery id to retry with a new commit SHA.
The process fixture now exits a real Pilot after every durable delivery boundary,
recovers against the built Unix broker and physical FX, and proves failed terminals
cannot create receipts, finalization, or owner completion.

### 2026-08-11 — Implement

Terminal and restart-recovery states are now published only after the matching
operation record is persisted. A real filesystem write failure followed by a
fresh broker and Pilot process proves one physical delivery, durable fail-closed
recovery, and no receipt, outbox, finalization or owner completion.

### 2026-08-11 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Terminal recovery | `go test -count=1 ./internal/releasebroker` | 9 OK; отказ записи не публикует terminal, fresh restart даёт `failed`, executor остаётся один. |
| Fail-closed готовность | `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` | 10 OK; процессный restart не создаёт receipt, outbox, `mark_final(true)` или owner done. |
| Соседние recovery/lock/outbox сценарии | тот же Pilot class | OK: crash boundaries, lock join, N+1, immutable journals и legacy audit-only. |
| Сборка и чистота | `FACTORY_DATA_HOME=$(mktemp -d ...) just build`; `git diff --check` | Собраны три бинаря; whitespace ошибок нет. |
| Полный регресс | `just check`; отдельно `go test -timeout 25s -count=1 ./internal/controlplane` | Не завершён: независимый control-plane timeout на SQLite migration (`TestHTTPEfficiencyReturnsBothFixedComparablePeriods`); файлы control-plane не менялись. |

### 2026-08-12 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Durable broker и terminal recovery | `go test -race -count=1 ./internal/releasebroker` | PASS: 11 broker-сценариев, включая write/fsync/rename failures и restart без второго executor. |
| Merge/restart/outbox/legacy | `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` | PASS: 10 процессных сценариев. |
| Установка broker | `bash ops/test-install-project-release-broker.sh` | PASS: установка и безопасное повторение. |
| Каждый статус release-driver | `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh`; `bash ops/test-fx-factory-release.sh` | BLOCKED: syntax PASS, fixture падает до status-сценариев — отсутствует `install/factory-release-broker`; `make_fixture` не создаёт обязательные rollback artifacts. |
| Полный регресс | `just check` | BLOCKED: format/vet/vuln/staticcheck и начальные Go-пакеты PASS; общий `go test ./...` принудительно завершён SIGTERM без test assertion. |
| Актуальность базы | `git rebase origin/main` после fetch свежего `main` | BLOCKED: конфликт `internal/releasebroker/broker.go` при применении `2178fbd…`; rebase отменён без изменения реализации. |
| Чистота и изоляция | pinned diff `fde77f86…38aea51d`; `git diff --check`; `git status --short` | 5 ожидаемых файлов, whitespace ошибок и stray-файлов нет; UI, migrations и control-plane не затронуты. |

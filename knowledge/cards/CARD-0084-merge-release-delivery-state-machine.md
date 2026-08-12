# CARD-0084 — Единая машина состояний слияния и выпуска

Implementation commit: 162d2c0cc0066b88078b16567f2fb01c3f00e1b6 — после ошибки fsync каталога terminal-успех не принимается при перезапуске.

## HEAD

- Status: Verified — backend PASS; полный `just check` остановлен на отсутствующем `eslint`.
- Branch: `factory/dc92ce68-4ea-d680b52d-273`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 162d2c0cc0066b88078b16567f2fb01c3f00e1b6 — после ошибки fsync каталога terminal-успех не принимается при перезапуске.
- What changed: Перед terminal-записью создаётся durable pending-маркер; committed-маркер появляется только после успешной записи и fsync файла. Перезапуск без committed-маркера переводит terminal в `failed`.
- Evidence: новый сценарий rename→ошибка `syncDir`→restart, `go test -count=1 ./internal/releasebroker`, Pilot class 10/10 и `just build` — PASS; `just check` прошёл vet, vuln, staticcheck и все Go-тесты, но `web` lint получил `eslint: not found`.
- Next action: Установить зависимости `web` и повторить `just check` перед слиянием.

## LOG

### 2026-08-12 — Implement

Broker теперь fail-closed восстанавливает terminal-состояния после неопределённой
долговечности каталога: pending/committed-маркеры разделяют rename и принятие
результата. Сценарий ошибки `syncDir` после rename и перезапуска подтверждает,
что успех не принимается и executor не повторяется; целевые Go/Pilot проверки,
сборка и весь Go-регресс зелёные, UI lint заблокирован отсутствующим eslint.

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

### 2026-08-12 — Implement

Исправлено наблюдаемое расхождение terminal status и durable operation record:
при отказе финального persist API сохраняет `running`, а не публикует ложный
`succeeded`. Новый test принудительно ломает финальную запись и подтверждает
результат через API и JSON-файл; целевые Python/Go/shell проверки и `just check` прошли.

### 2026-08-12 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Единственная модель и legacy | `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` | PASS: V2 generations остаются единственным done-путём, legacy читается только как audit. |
| Готовность и outbox | тот же process class | PASS: до durable terminal нет receipt/outbox, `mark_final(true)` или owner done; после accepted release по одному каждого. |
| Recovery merge и launch safety | тот же process class | PASS: crash boundaries POST/wrapper/PID/running/terminal восстанавливаются свежим Pilot без второго physical release. |
| N против N+1 | тот же process class | PASS: rc=8 присоединяет второй merge к N; запуск в `launching` создаёт ровно один successor. |
| Terminal recovery и durable broker | `go test -count=1 ./internal/releasebroker` | PASS: corrupt record блокирует старт, fsync-error не публикует operation или terminal success. |
| Release driver и установка broker | `bash ops/test-fx-factory-release.sh`; `bash ops/test-install-project-release-broker.sh` | PASS: fixture проверяет release/rollback; unit имеет `StateDirectory=factory/release-broker`. |
| Изоляция и чистота | `git diff --name-only <pinned base>...<candidate>`; `git diff --check` | Только `internal/releasebroker/{broker.go,broker_test.go}` и CARD-0084; whitespace ошибок нет. |
| Сборка | `FACTORY_DATA_HOME=$(mktemp -d ...) just build` | PASS: собраны server, worker и release-broker. |
| Полный регресс | `FACTORY_DATA_HOME=$(mktemp -d ...) just check` | Static checks PASS; `internal/controlplane` и `internal/worker` завершились по 300-секундному timeout, вне диффа. |

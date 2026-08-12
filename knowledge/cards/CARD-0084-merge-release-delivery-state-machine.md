# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/f22a0c29-3e3-9826683e-740`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 4e1c5906a4d5e8571904a132d3113e51e268b8ca — финальная запись broker синхронизируется с диском.
- What changed: Temp record проходит file fsync/close, atomic rename и directory fsync до публикации terminal status; неоднозначный directory-sync откатывается к предыдущей durable записи.
- What changed: Детерминированные sync/close/rename faults и fresh restart подтверждают fail-closed статус и единственный executor; Pilot остаётся выключенным.
- Evidence: чистый `go test -timeout 5m ./...` в составе `just check` → PASS (включая broker); 11 state-machine сценариев Pilot → PASS; обе shell fixture → PASS; `just build` → PASS. `ui-check` не запущен до конца: в окружении отсутствует `web/node_modules/eslint`, а UI не менялся.
- Next action: Владелец проверить и влить поставку.

## LOG

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

### 2026-08-11 — Implement

The release driver now checks its authoritative final `succeeded` write and
returns a non-success result when that atomic rename fails after physical
delivery. A real shell fault plus fresh broker and Pilot processes prove one
executor, durable failure and no receipt, outbox, finalization or owner completion.

### 2026-08-11 — Implement

Broker now fsyncs every operation temp file and its containing directory before
publishing a terminal result. Deterministic file-sync, close, rename and
directory-sync faults retain the previous durable record; a fresh broker fails
it closed without another executor. Broker race, 20 durability repetitions,
213 Pilot tests, both shell fixtures, `just check`, build and diff all passed.

### 2026-08-11 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Единственная V2-модель и legacy audit-only | `MergeReleaseDeliveryStateMachineTests` | PASS: 11 сценариев, включая legacy и generation boundaries |
| Recovery, N/N+1, launch и terminal safety | тот же Python-набор; `go test -timeout 5m ./...` | PASS: restart/crash, lock-join и fail-closed сценарии; broker-пакет PASS |
| Durable terminal запись | `go test -timeout 5m ./...` | PASS: `TestTerminalWriteFailureNeverPublishesSuccessOrRepeatsExecutorAfterRestart` и sync-fault coverage |
| Outbox и owner completion | `MergeReleaseDeliveryStateMachineTests` | PASS: terminal failure не создаёт ложный done/receipt |
| Release driver и broker installation | `bash ops/test-fx-factory-release.sh`; `bash ops/test-install-project-release-broker.sh` | PASS: одна установка/общий откат; StateDirectory и restart upgrade проверены |
| Изоляция и чистота diff | `git diff --check`; git-verified three-dot file list | PASS: только Pilot/broker/release-driver, tests, spec и CARD-0084; UI/control-plane/migrations не затронуты |

Полный `just check` прошёл Go vet, vuln, staticcheck и Go tests, но остановился
на `web` UI lint: `eslint` отсутствует в окружении. Это внешняя зависимость
неизменённой UI-области; относящиеся к поставке проверки выше прошли.

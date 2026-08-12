# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: BLOCKED — свежий `main` конфликтует с поставкой при обязательном rebase.
- Branch: `factory/4b80f667-aa4-f342742f-30a`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 380e77b1223a16a6608134e3d002f0d9629988ad — retry после `rc=8` сохраняет неизменный adapter/target и реальные crash boundaries.
- What changed: Broker принимает новый SHA того же delivery id только при том же adapter/target; rollback и чужой target атомарно отклоняются.
- What changed: Реальный FX PID и terminal phase сохраняются до recovery; отдельные Pilot-процессы проверяют post/wrapper_status/pid/running/terminal без ручной подмены phase.
- Evidence: `python3 -m unittest -v pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` → OK (9); `go test -race ./internal/releasebroker` → OK; `bash ops/test-fx-factory-release.sh` и `bash ops/test-install-project-release-broker.sh` → OK. `just check` дошёл до `go test ./...`, где таймаутился неизменённый `internal/worker`.
- Next action: Интегрировать конфликты с `main`, затем повторить Verify на перебазированной поставке.

## LOG

### 2026-08-12 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Единая V2-модель и terminal safety | 9 process-level Pilot сценариев | reserved/launching/running/completed/failed сохраняются, failed не создаёт done |
| Recovery, N/N+1 и outbox | те же Pilot-сценарии с реальным Unix broker | один receipt/outbox, lock join остаётся N, successor создаётся после launch |
| Неизменность delivery | `go test -race ./internal/releasebroker` | OK; adapter/target mutation отклоняется, retry того же id допустим |
| Физический FX и installer | обе shell fixture | OK; повторная доставка не устанавливает второй раз, StateDirectory устанавливается |
| Полная регрессия | `just check` | внешний `internal/worker` timeout через 300s; изменённые Pilot/broker/FX области прошли |
| Интеграция | `git rebase origin/main` (base `8d98fee`) | BLOCKED: конфликты в Pilot, broker, FX, тестах, CARD-0084 и спецификации; rebase безопасно отменён |

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

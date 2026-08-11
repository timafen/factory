# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Implemented — готово к повторному review.
- Branch: `factory/c5420272-51f-199aa460-48e`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 8e0f448f01f57ad499078f7d455bbcc49b5b9b9c — Pilot V2 и broker безопасно восстанавливают один выпуск.
- What changed: Pilot POST использует `/v1/operations`; intent → journal → wait и outbox имеют durable idempotent границы.
- What changed: `rc=8` оставляет generation reserved, присоединяет свежий SHA и повторно исполняет только тот же immutable id.
- Evidence: `python3 -m unittest pilot.test_pilot` → OK (206, 13 skipped); `go test ./internal/releasebroker` → OK; `bash ops/test-fx-factory-release.sh` → PASS; `just check` → passed.
- Next action: Review проверить diff CARD-0084 и смержить при отсутствии новых замечаний.

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

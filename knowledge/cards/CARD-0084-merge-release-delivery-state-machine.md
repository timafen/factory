# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Implemented — исправления review готовы к повторной проверке.
- Branch: `factory/922d676e-7e3-bf047ab5-9de`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 3085c03f25cfa2184abff882f93185ffd46e86d3 — реальный Unix broker подтверждает восстановление одного выпуска.
- What changed: Pilot-тест собирает и запускает Go broker на Unix-сокете, проходит API и один физический FX executor.
- What changed: Все restart boundaries считают merge/POST/physical/owner done; `rc=8` retry завершает тот же N без N+1.
- Evidence: `python3 -m unittest pilot.test_pilot` → OK (206, 13 skipped); `go test ./internal/releasebroker` → OK; shell fixtures → OK; `just check` → passed.
- Next action: Review проверить три исправленных доказательства CARD-0084.

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

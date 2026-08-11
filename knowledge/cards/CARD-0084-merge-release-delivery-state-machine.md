# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Implemented — ожидает review/merge.
- Branch: `factory/b128a09a-9e3-2604fc3e-ac3`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: cad7c2956d624309311fe34ccbe2719e5aca2da7 — Pilot V2, durable broker и generation-aware FX driver.
- What changed: V2 хранит immutable generation/waits/outbox и не завершает Verify до accepted release; legacy state сохранён только в audit.
- What changed: broker/driver переживают повтор одного delivery id без второго физического выпуска; systemd даёт broker durable StateDirectory.
- Evidence: `python3 -m unittest pilot.test_pilot` → OK (старые tests skipped); `go test ./internal/releasebroker` → OK; `bash ops/test-fx-factory-release.sh` → PASS; `just check` → passed.
- Next action: Review проверяет поведение на production-like broker socket после merge.

## LOG

### 2026-08-11 — Specification

Specification was accepted for implementation on a fresh main branch. It requires
a durable V2 generation model, immutable broker operations, generation-bound
owner completion and audit-only legacy migration.

### 2026-08-11 — Implement

Implemented the V2 generation lifecycle in Pilot, including intent recovery
before the processed cursor, reserved-N joins, successor requests, delivery
receipts and a durable notification outbox. Broker operations now persist their
immutable request/status to StateDirectory and the FX fixture proves a repeated
delivery id does not perform a second release. Evidence: targeted Python and Go
tests, both shell fixtures, and `just check` passed on this branch.

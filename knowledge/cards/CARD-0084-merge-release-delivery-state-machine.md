# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Implemented — надёжный выпуск перенесён на свежую `main` без включения Pilot.
- Branch: `factory/4c25e502-88d-2806b81a-1a0`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: abf5b480e3446873495a4e38f176ab2febb8902a — fail-closed финальная запись драйвера перенесена поверх свежей основной ветки.
- What changed: Durable terminal persistence, immutable delivery identity и единственный физический executor сохранены поверх base `36ce322e2b6685dd9a87f4d2c947f61538654ae1`.
- What changed: Fresh-review поведение CARD-0087 сохранено; Pilot/live Workflow revisions не включались.
- Evidence: broker `-race` → PASS; real process regression → 11 PASS; полный Pilot → 213 PASS, 13 skipped; обе shell fixture → PASS.
- Evidence: `just check`, `just build`, `git diff --check` → PASS; three-dot → `behind_by=0`.
- Next action: Strict Review проверить интеграционную ветку CARD-0084 относительно свежей `main`.

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

Надёжный release broker, Pilot и release driver перенесены на `main` из PR134;
fresh-review поведение CARD-0087 сохранено, Pilot не включён. Broker race,
11 restart/write-failure тестов, полный Pilot (213), обе shell fixture,
`just check`, `just build` и three-dot сравнение прошли; открытых рисков нет.

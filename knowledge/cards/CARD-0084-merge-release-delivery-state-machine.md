# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Implemented — ожидает проверки и слияния.
- Branch: `factory/594bc805-676-fff208e1-843`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 0432dced97bd128b238a8bb5ee03c57dc7be3789 — проверка locked retry читает исходную операцию и подтверждает durable POST.
- What changed: Повторная доставка после снятия блокировки проверяется без ложной паники; terminal-status write failure покрыт shell и реальным Pilot/broker restart.
- What changed: Реализация fail-closed остаётся на свежем `main`; перенесены только отсутствовавшие регрессионные проверки.
- Evidence: broker `-race` → PASS; Pilot process tests → 11 PASS; shell fixtures, install fixture, TypeScript и build → PASS.
- Next action: Review проверить три целевых теста относительно свежего `main`.

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

### 2026-08-11 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Terminal recovery | `go test -count=1 ./internal/releasebroker` | 9 OK; отказ записи не публикует terminal, fresh restart даёт `failed`, executor остаётся один. |
| Fail-closed готовность | `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` | 10 OK; процессный restart не создаёт receipt, outbox, `mark_final(true)` или owner done. |
| Соседние recovery/lock/outbox сценарии | тот же Pilot class | OK: crash boundaries, lock join, N+1, immutable journals и legacy audit-only. |
| Сборка и чистота | `FACTORY_DATA_HOME=$(mktemp -d ...) just build`; `git diff --check` | Собраны три бинаря; whitespace ошибок нет. |
| Полный регресс | `just check`; отдельно `go test -timeout 25s -count=1 ./internal/controlplane` | Не завершён: независимый control-plane timeout на SQLite migration (`TestHTTPEfficiencyReturnsBothFixedComparablePeriods`); файлы control-plane не менялись. |

### 2026-08-12 — Implement

После переноса на свежий `main` сохранены только три отсутствовавшие регрессии:
отказ финальной записи статуса, process restart Pilot/broker и durable POST после lock retry.
`go test -race -count=1 ./internal/releasebroker`, 11 процессных Pilot-тестов,
обе shell-fixtures, `npx tsc -p tsconfig.app.json --noEmit` и `just build` прошли.

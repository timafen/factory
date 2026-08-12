# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Verified PASS — ожидает слияния человеком.
- Branch: `factory/12526369-3a4-e69c5117-acd`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 81d67ac49275d0fc24fa4380a246aa431d956f15 — повреждённый или неопределённый статус не запускает executor повторно, а release-driver сохраняет переходы durable.
- What changed: Каждый статус driver проходит запись, file fsync, atomic rename и directory fsync; при неопределённом terminal-переходе сохранён `running`.
- What changed: Broker fail-closed сохраняет `locked` и не повторяет физический выпуск после повреждённого состояния.
- Evidence: `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh`, `go test -race ./internal/releasebroker`, `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests`, `npx tsc -p tsconfig.app.json --noEmit` → PASS.
- Next action: Человеку принять решение о слиянии.

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

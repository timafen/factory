# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Verified PASS — ожидает человеческого merge.
- Branch: `factory/e783f445-945-25356772-a70`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: 0c3997247d848a6df447b705f92600f09f4d9f60 — реальный broker и отдельные Pilot-процессы доказывают recovery выпуска.
- What changed: Каждая crash boundary запускается через отдельный persisted Pilot process и восстанавливается свежим process против собранного Go broker.
- What changed: Broker сохраняет счётчик POST; lock retry сохраняет N, принимает SHA второго merge до первого принятого выпуска и достраивает completed receipts после restart.
- Evidence: 7 настоящих process/crash сценариев, disk-backed broker и обе shell fixture прошли; `just check` дошёл до полного Go-набора, где независимые controlplane/worker SQLite-тесты исчерпали лимит 5 минут.
- Next action: Человеку проверить и слить кандидатскую ветку; отдельно разобрать нестабильность SQLite `fsync` в общем наборе.

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

Strict review correction replaces the in-memory phase fixture with independent
Pilot interpreter invocations over one persisted state/journal and the built
Unix broker. The broker durably records every POST; a locked N accepts the
second merge snapshot before its single successful physical installation, and
recovery from durable `completed` writes its missing receipts/outbox exactly once.

### 2026-08-12 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Recovery merge, launch safety, terminal recovery, outbox | `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` | 7 сценариев с собранным Go broker и отдельными Pilot-процессами прошли: каждая crash boundary заканчивается одним POST/physical release и одним owner done. |
| N против N+1 и правильная готовность | та же process-fixture | locked retry присоединяет второй merge к N, успешная установка одна; receipt/outbox и `mark_final` создаются только при terminal success. |
| Durable broker | `go test ./internal/releasebroker` | PASS: immutable duplicate, restart, status-before-PID и единственный executor проверены. |
| Release driver и systemd upgrade | `bash ops/test-fx-factory-release.sh`; `bash ops/test-install-project-release-broker.sh` | PASS: повторный delivery id не выполняет вторую установку; активный broker обновляется restart, с `StateDirectory`. |
| Изоляция | pinned diff `fc3af293e5e2b2c3802ad9b1d376f7796aa3b067...a5ad2bde5728e1941fcd71078a96fab089318dca` | Нет UI, migration или control-plane файлов; `git diff --check` чист. |
| Полный набор | `just ui-install && just check` | BLOCKED вне области: `internal/controlplane` и `internal/worker` превысили 5-минутный лимит в SQLite `fsync`/checkpoint; все проверенные компоненты выпуска прошли. |

# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Implemented PASS — готово к Review.
- Branch: `factory/56574781-e4b-7c963a00-510`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
Implementation commit: 5f2dca4e10002bfdc638736f4243a169fd5a65b6 — регрессия закрепляет fail-closed отказ NewAt для каталога `delivery-1.json`.
- What changed: Проверка типа выполняется для каждого пути с суффиксом `.json`; каталог и иной не-регулярный путь завершают `NewAt` ошибкой.
- What changed: Регрессионный тест подтверждает ошибку запуска и отсутствие физического вызова executor для `.json`-каталога.
- Evidence: `go test -count=1 ./internal/releasebroker` → OK; `just build` → бинарники собраны.
- Next action: Review повторно проверяет fail-closed обработку `.json` durable-записей.

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

Исправлено наблюдаемое расхождение terminal status и durable operation record:
при отказе финального persist API сохраняет `running`, а не публикует ложный
`succeeded`. Новый test принудительно ломает финальную запись и подтверждает
результат через API и JSON-файл; целевые Python/Go/shell проверки и `just check` прошли.

### 2026-08-12 — Implement

Broker recovery теперь fail-closed отвергает повреждённые, подменённые и
неканоничные durable operation-записи вместо их молчаливой потери и возможного
повторного физического выпуска. Обычный и race Go-прогоны, 10 Pilot-сценариев,
release-driver/installer fixtures и сборка зелёные; полный `just check` подтвердил
broker, но остановился на прежних пятиминутных timeout control-plane и worker.

### 2026-08-12 — Implement

Поставка восстановлена поверх свежего `origin/main` без посторонних файлов.
Обычный и race-прогоны broker, 10 процессных Pilot-сценариев, release-driver,
installer и сборка подтвердили fail-closed recovery; systemd fixture штатно
пропущен в непривилегированном окружении.

### 2026-08-12 — Implement

`.json`-каталог больше не пропускается как отсутствующая durable operation:
`NewAt` завершает запуск ошибкой до чтения состояния. Регрессионный тест
подтверждает ноль вызовов executor; обычный и race Go-прогоны broker, а также
`just build`, прошли успешно.

### 2026-08-12 — Implement

Регрессия приведена к точному сценарию владельца с каталогом `delivery-1.json`.
После перебазирования на свежий `origin/main` целевой Go-тест подтвердил отказ
`NewAt` до вызова executor, а `just build` успешно собрал бинарники.

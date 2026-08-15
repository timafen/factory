# CARD-0084 — Единая машина состояний слияния и выпуска

Implementation commit: f34cd15f0aa5e2f9fa9fa8bfaecde89a4519d81a — ошибка финальной записи выпуска возвращается как неуспех и запускает откат.

## HEAD

- Status: Implemented — финальная запись выпуска проверена после перебазирования на свежий `main`.
- Branch: `factory/9f36bf7a-c67-e40c5cc6-26e`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: f34cd15f0aa5e2f9fa9fa8bfaecde89a4519d81a — ошибка финальной записи выпуска возвращается как неуспех и запускает откат.
- What changed: публикация `current`, `previous` и журнала `committed` объединена в fail-closed цепочку; отказ не становится успешным выпуском.
- Evidence: `go test -count=1 ./internal/releasebroker` — PASS; `bash ops/test-fx-factory-release.sh` — PASS; `bash -n` и `git diff --check` — PASS.
- Next action: Verify проверить свежую ветку по закреплённому implementation SHA.

## LOG

### 2026-08-14 — Implement

Финальные указатели выпуска и запись `committed` объединены в одну проверяемую
цепочку: отказ записи возвращает код 7, откатывает прежний комплект и не
печатает успешный результат. Shell-fixture воспроизводит отказ `current`, а
broker-тест отдельно подтверждает отображение кода 7 как `rollback_failed`.

Доказательство: `go test -count=1 ./internal/releasebroker`,
`bash ops/test-fx-factory-release.sh`, `bash -n` и `git diff --check` прошли.

### 2026-08-14 — Implement

Перебазировано на `origin/main` `f1db2b40`; implementation commit после
перебазирования закреплён отдельной строкой. Полный Go-регресс прошёл; первая
общая проверка остановилась из-за отсутствующего локального `eslint`, после
штатного `npm ci` UI lint и typecheck прошли. Риск: `npm audit` сообщает две
high-severity зависимости, не затрагивающие эту поставку.

### 2026-08-14 — Implement

Восстановление выполнено на свежем `origin/main`, где защита terminal write уже
присутствует. Regression усилен вторым свежим запуском broker: durable `failed`
сохраняется, а executor остаётся вызван ровно один раз. Целевые Go-тесты прошли;
10 реальных Pilot→broker сценариев также прошли.

### 2026-08-12 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Реальный цикл Pilot→broker | `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` | 10 PASS: Unix-socket POST, restart/recovery, lock join и отсутствие повторного физического executor. |
| Durable terminal v1 | `go test -count=1 ./internal/releasebroker` | PASS: `.commit` marker подтверждает terminal, неподтверждённый terminal fail-closed восстанавливается как `failed`. |
| Legacy terminal | тот же Go-пакет, `TestDiskBrokerPreservesLegacyTerminalStatusesWithoutExecutor` | PASS: статусы старого формата сохраняются без запуска executor. |
| Полный регресс Go/Python | `just test` | PASS: `go test -timeout 5m ./...` и 10 Python-тестов завершились успешно. |
| Чистота поставки | pinned diff и `git diff --check` | Только `internal/releasebroker/{broker.go,broker_test.go}` и данная карточка; whitespace ошибок нет. |

### 2026-08-12 — Implement

Новые durable operation-записи помечаются версией 1, поэтому двухфазный
`.commit` проверяется только для них. Legacy terminal-записи без версии после
restart сохраняют `succeeded`, `locked`, rollback или `failed` без повторного
executor. Целевой Go-пакет и `just build` прошли; последний `just check`
остановлен прежним SA4000 вне области задачи.

### 2026-08-12 — Implement

Перебазировано на свежий `origin/main`; удалена неиспользуемая проверка
operation, найденная full staticcheck. `go test -count=1
./internal/releasebroker`, 10 Pilot-сценариев и оба shell-fixture прошли.
`just build` прошёл; `just check` останавливается только на прежнем SA4000 в
неизменённом `internal/worker/attempt_lifecycle_test.go`.

### 2026-08-12 — Implement

В `web/` зависимости восстановлены через штатный `npm ci`, без глобальной
установки `eslint` и изменений lockfile. После этого TypeScript, UI lint и
`just check` завершились успешно; после rebase целевой broker-тест повторно
подтвердил fail-closed recovery при ошибке fsync каталога.

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

### 2026-08-12 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Повреждённая durable-запись не запускает выпуск | `go test -count=1 -timeout 5m ./internal/releasebroker` | OK: `delivery-1.json` как каталог отклонён до вызова executor. |
| Прочие некорректные `.json`-записи fail-closed | тесты `TestDiskBrokerFailsClosedOnInvalidOperationState` и `TestDiskBrokerFailsClosedOnJSONDirectory` | OK: corrupt JSON, чужое имя, неверный adapter/status и каталог не восстанавливаются. |
| Соседнее восстановление | тот же пакет | OK: terminal state сохраняется после restart, незавершённый запуск становится `failed`, повторный executor не запускается. |
| Полный проектный регресс | `just check` | Форматирование, `vet`, `govulncheck`, `staticcheck` и `internal/releasebroker` OK; вне области timeout 5m: `internal/controlplane`, `internal/worker` (включая flaky worker integration tests). |

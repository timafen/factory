# CARD-0084 — Единая машина состояний слияния и выпуска

Implementation commit: 1449b7f344161590eb436ccae60bdc60c8b7ff74 — release-driver сохраняет отказанный authoritative-статус неизменным и надёжно пишет собственные переходы.

## HEAD

- Status: Implemented — ready for Review.
- Branch: `factory/ac06d0d4-35f-9eec718c-8c1`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: `1449b7f344161590eb436ccae60bdc60c8b7ff74` — release-driver сохраняет отказанный authoritative-статус неизменным и надёжно пишет собственные переходы.
- What changed: root-owned каталог 0700 и fail-closed проверки защищают статусы; EXIT-trap включается только перед собственным durable-переходом и не перезаписывает неизвестное состояние.
- Evidence: release-driver/installer fixtures, releasebroker Go-тесты, `just staticcheck`, `just build` — PASS; свежий `origin/main` также прошёл `staticcheck` без U1000.
- Next action: Провести Review поставки.

## LOG

### 2026-08-15 — Implement

Каталог authoritative-статусов перенесён под systemd `StateDirectory` с root-owned
mode 0700. release-driver fail-closed проверяет реальный каталог, владельца и
права перед записью; installer-fixture подтверждает защитные проверки, shell и
Go-проверки прошли.

### 2026-08-15 — Implement

По утверждённому ответу владельца `locked` сохранён как итог lock-конкуренции,
а повтор с тем же immutable operation ID заново захватывает lock и успешно
завершается. EXIT-ловушка вооружается до первой durable-записи `launching`;
shell-fixture подтвердил terminal `succeeded` и ровно один физический выпуск.

### 2026-08-15 — Implement

Реализация перенесена на свежий `origin/main`; ранние ошибки после durable
`launching` завершают операцию статусом `failed`, а fail-closed recovery не
запускает второй физический выпуск. Профильные Go- и shell-проверки, а также
сборка прошли после перебазирования.

### 2026-08-15 — Implement

По утверждённому ответу владельца исправлены оба блокера Review: повреждённый
authoritative status теперь fail-closed запрещает повторный выпуск, а ранняя
ошибка после durable `running` сохраняет terminal `failed`. Добавлены отдельные
fixture-сценарии, подтверждающие отсутствие физического выпуска и terminal status.

### 2026-08-15 — Implement

Исправлены четыре замечания Review: locked delivery повторно захватывает lock,
каждый выход после running оставляет terminal status, а результаты отката не
теряют классификацию. Shell-fixture покрывает retry, terminal preflight и
успешный автоматический откат; профильный broker-тест и сборка прошли.

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

### 2026-08-15 — Implement

Перебазирована остановленная реализация на свежий `origin/main`, сохранена
durable-запись каждого статуса release-driver и исправлено ожидание проверки
сбоя directory fsync: после неопределённого terminal остаётся `running`, а
перезапуск fail-closed переводит операцию в `failed` без второго executor.
Профильные Go race, Pilot, shell fixture и build прошли.

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

### 2026-08-15 — Implement

После durable `launching` минимальная EXIT-ловушка сразу фиксирует `failed`,
поэтому ошибки подготовки и захвата release lock не оставляют delivery в
неопределённом состоянии. Shell-fixture подтверждает terminal `failed` для
lock/preflight и успешный повторный выпуск с новым delivery ID; Go-пакет и сборка прошли.

### 2026-08-15 — Implement

Кандидат перебазирован на свежий `origin/main`; неизвестный authoritative-статус
теперь остаётся неизменным, а собственные переходы драйвера сохраняются fail-closed.
Полный release-driver fixture, installer fixture, releasebroker Go-тесты,
`staticcheck` и сборка прошли; U1000 отсутствует и на main, и в кандидате.

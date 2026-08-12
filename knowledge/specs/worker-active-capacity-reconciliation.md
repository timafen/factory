# Спецификация: счётчик занятости воркера сам восстанавливается

> **Статус повторной постановки (2026-08-12):** по утверждённому решению
> владельца эта работа закрывается как повтор
> [CARD-0085](../cards/CARD-0085-worker-active-capacity-reconciliation.md).
> Новая реализация и следующие этапы не запускаются: требуемое поведение уже
> находится в свежем `main`. Эта запись оставляет проверяемую связь повтора с
> поставкой и не меняет продуктовый код.

## Цель и влияние на владельца

Владелец получает всю настроенную параллельность без ручного рестарта воркера.
После потери ответа `complete`, отмены, истечения lease, перезапуска worker или
control plane свободный слот определяется заново из живых попыток, а не из
устаревшего process-local счётчика. Это устраняет «призрачный» занятый слот и
сохраняет защиту от второго назначения реально работающему supervisor.

Retained dirty/cancelled worktree остаётся доказательством для cleanup и лимитом
репозитория (`retained_count`/`capacity_acknowledged`), но не является активной
сессией и не уменьшает `worker.capacity`.

## Технический подход и реальные файлы

До реализации CARD-0085 `internal/worker/registration.go` передавал `len(manager.slots)` как
`WorkerRegistration.ActiveCount`; `internal/controlplane/store.go` сохранял его
в `workers.active_count`, и `selectTaskRouteWithSourceRequirement` использовал
сохранённое значение как load. В то же время `internal/controlplane/state.go`
уже считает `attempts` в `preparing`/`running` для `Claim`, а `SweepExpired`
переводит истёкшие lease в `lost`. Эти два источника расходятся после сбоя.

Реализация вводит в control plane одну транзакционную функцию сверки worker:

- до расчёта capacity она условно завершает только истёкшие `preparing`/`running`
  попытки как `lost`, переводит их execution из активного состояния ровно один
  раз и возвращает фактически изменённые attempt ID;
- её единственный active-count — число попыток данного worker в
  `preparing`/`running` с lease, действующим на серверном времени; это значение
  применяется в `Claim`, маршрутизации, `Worker`/`Workers` и registration;
- `workers.active_count` становится совместимым материализованным снимком,
  который сервер обновляет только полученным derived значением. Входящий
  `ActiveCount` старого worker принимается для wire compatibility, но не влияет
  на admission, load или отображаемый ответ;
- registration, claim, attempt heartbeat/start/complete, cancel и periodic sweep
  вызывают общий путь там, где изменяется активное множество. Условные `UPDATE`
  по текущему состоянию сохраняют exactly-once переход при гонке completion,
  sweep и повторе HTTP-запроса;
- worker при startup/reconnect сначала завершает локальную manifest/supervisor
  сверку из `internal/worker/reconcile.go`, затем registration. Его `slots`
  остаётся локальным ограничителем запуска, но не является server authority;
  worker не начинает второй supervisor для attempt, уже находящегося в `active`.

В `main` добавлена `migrations/026_worker_capacity_reconciliations.sql`: append-only
журнал с worker ID, временем, trigger (`registration`, `claim`, `heartbeat`,
`terminal`, `sweep`), прежним cached/reported count, derived count и числом
освобождённых ghost slots. Миграция нужна для наблюдаемого события и оконной
метрики; миграции для удаления `workers.active_count` не требуется, поскольку
столбец остаётся обратносуместимым кэшем. `protocol.MetricsSummary` и
`internal/controlplane/metrics.go` отдают число reconciliations и ghost slots
за окно; structured server events логируют только фактическую коррекцию и не
выдают retained worktrees за active slots.

Фактическая поставка, уже находящаяся в `main`:
`migrations/026_worker_capacity_reconciliations.sql`,
`internal/protocol/types.go`,
`internal/controlplane/{metrics.go,metrics_test.go,state.go,store.go,store_test.go}`
и `internal/worker/{registration.go,worker_integration_test.go}`. UI не
меняется.

## Последовательный план

Для повторной постановки выполнены только следующие действия:

1. Сверить свежий remote `main` с назначенной веткой и подтвердить, что
   canonical implementation уже присутствует в `main`.
2. Запустить две целевые регрессии: stale cached count и restart/reconnect после
   потерянного ответа `/complete`.
3. Зафиксировать решение владельца в этой спецификации и CARD-0085; не создавать
   product diff и не запускать следующие этапы.

### Исторический план реализованной CARD-0085

1. Добавить migration `026` с журналом сверок, индексом по времени/worker и
   тестом upgrade `025 -> 026`; оставить старый `active_count` без destructive
   schema change.
2. Вынести в `store.go` транзакционный derived-count и expiry/reconcile helper;
   заменить все route/load/read queries, которые читают cached `active_count`.
3. Пропустить helper через registration, Claim, terminal/cancel и SweepExpired;
   сохранять кэш только derived значением и писать одну запись/событие только
   при расхождении либо освобождении ghost slot.
4. Обновить protocol/HTTP/metrics так, чтобы worker response и Metrics были
   derived и окно считало журнал, а не текущий cache.
5. Убрать из worker registration смысл authority у `len(slots)`, сохранив поле
   только на время совместимости; на startup/reconnect завершить reconciliation
   manifest до registration и не создать duplicate supervisor.
6. Добавить store, HTTP и integration regression tests; выполнить целевую Go
   команду и `git diff --check`.

## Критерии приёмки

1. При capacity=2 искусственно сохранённый `active_count=1` и отсутствие
   живых attempt не блокируют route/claim: две queued задачи получают две lease
   без рестарта worker.
2. `preparing` и `running` с неистёкшим lease занимают ровно один слот каждый;
   повторный claim не превышает capacity и не создаёт второго supervisor.
3. `succeeded`, `failed`, `cancelled` и `lost`, включая гонку `complete` против
   sweep, освобождают slot ровно один раз; повтор completion остаётся
   идемпотентным.
4. Потерянный response completion, restart worker и restart control plane не
   оставляют capacity занятым после следующей registration/claim/sweep; до
   lease expiry реальная running попытка продолжает резервировать слот.
5. Retained dirty/cancelled worktree виден в retained capacity репозитория, но
   derived worker active count для его terminal attempt равен нулю.
6. API/метрики показывают derived active count, число reconciliation и ghost
   slots за выбранное окно; запись/лог создаётся только для настоящей коррекции.
7. Upgrade существующей базы проходит без ручной миграции данных, rollback
   безопасен: остановить новые бинарники, восстановить предыдущие и не удалять
   журнал/столбец. До rollback не оставлять активные attempts без штатного
   lease-expiry/sweep; старый бинарь может читать сохранённый cache, поэтому
   rollback допустим только после drain либо с ожидаемым временным conservative
   under-utilization, а не с риском double assignment.

## Тест-план

Для закрытия повтора обязательна уже существующая целевая команда:
`go test -race -timeout 10m ./internal/controlplane ./internal/worker -run '^(TestClaimReconcilesStaleCachedCapacityWithoutWorkerRestart|TestReconnectAfterLostCompletionRestoresEveryWorkerSlot)$' -count=1`.
Она должна завершаться с кодом 0 и одновременно доказывает, что stale счётчик
не блокирует оба слота, а restart после потерянного completion возвращает всю
ёмкость без дублирования живого supervisor.

- `internal/controlplane/store_test.go`: seeded stale `workers.active_count`,
  two queued совместимые задачи и два claim; assert оба slots заполнены,
  `active_count` в Worker derived и reconciliation записан.
- Там же table-driven гонки: terminal completion/replay, cancellation и expired
  lease против sweep; проверять один terminal transition, один release и
  отсутствие extra claim до/после правильной границы lease.
- `internal/controlplane/metrics_test.go` и `http_test.go`: окно метрик и
  worker JSON считают journal-derived values, не retained worktree и не stale
  input registration.
- `internal/worker/worker_integration_test.go`: оборвать успешный `/complete`
  response, перезапустить manager/control-plane fixture и доказать, что
  последующие queued jobs занимают весь `MaxConcurrent`; отдельный barrier
  доказывает, что живой supervisor не дублируется.
- `internal/worker/registration_test.go`/`reconcile` tests: reconnect с
  terminal retained manifest не рекламирует active slot; живой active handle
  не получает повторный запуск.
- Обязательная regression-команда должна завершаться кодом 0 и включать новый
  тест stale-count/full-capacity; перед merge дополнительно выполнить
  `go test ./internal/controlplane ./internal/worker` и `git diff --check`.

## Риски и решения

- Повторная реализация уже поставленного поведения могла бы разойтись с
  canonical code. Поэтому текущая работа ограничена документацией о закрытии,
  а основанием служат свежий `main` и целевые регрессии CARD-0085.
- Гонка sweep/complete может перезаписать исход. Все операции остаются в одной
  SQLite transaction и меняют строку только из active state; только winner
  публикует release/event.
- Использование client clock исказит capacity. Lease проверяется исключительно
  `Store.now()`, registration count используется лишь как diagnostic evidence.
- Aggressive reset на worker restart может убить реальную работу. До истечения
  lease active attempt остаётся capacity owner; local manifest identity и
  supervisor process identity fence duplicate execution.
- Смешение retained и active сломает лимит repo. Retention handoff остаётся в
  существующих `worker_repositories`/`capacity_acknowledged`; новая сверка его
  не подтверждает и не считает как slot.
- Журнал может расти. Индексировать по времени и применять тот же явный
  retention policy, что у operational metrics; агрегаты никогда не выводить из
  удалённого текущего cache.

## Карточка работы

`knowledge/cards/CARD-0085-worker-active-capacity-reconciliation.md`

ГОТОВО-КОГДА: файл migrations/026_worker_capacity_reconciliations.sql
ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл internal/controlplane/metrics.go
ГОТОВО-КОГДА: файл internal/controlplane/metrics_test.go
ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл internal/controlplane/store.go
ГОТОВО-КОГДА: файл internal/controlplane/store_test.go
ГОТОВО-КОГДА: файл internal/worker/registration.go
ГОТОВО-КОГДА: файл internal/worker/worker_integration_test.go
ГОТОВО-КОГДА: команда go test -race -timeout 10m ./internal/controlplane ./internal/worker -run '^(TestClaimReconcilesStaleCachedCapacityWithoutWorkerRestart|TestReconnectAfterLostCompletionRestoresEveryWorkerSlot)$' -count=1

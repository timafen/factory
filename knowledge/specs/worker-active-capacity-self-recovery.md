# Спецификация: счётчик занятости воркера сам восстанавливается

## Цель и влияние на владельца

Владелец не теряет настроенную параллельность после потерянного ответа
`/complete`, отмены, истечения lease или перезапуска worker/control plane.
Свободный слот определяется по живым server-side попыткам, поэтому фантомный
локальный счётчик не требует ручного рестарта и не допускает второго запуска
реально работающего supervisor.

Terminal retained worktree по-прежнему участвует в лимите репозитория через
`retained_count` и `capacity_acknowledged`, но не занимает активный слот
воркера. UI и его контракты не меняются.

## Технический подход и реальные файлы

Авторитетное значение `active_count` — число попыток данного worker в состояниях
`preparing` или `running` с `lease_expires_at` позже server time. Локальные
`Manager.slots` ограничивают только запуск процесса; `ActiveCount` в
`internal/worker/registration.go` остаётся wire-совместимым полем и не может
быть источником admission/load.

`internal/controlplane/state.go` выполняет транзакционную reconciliation:
условно переводит только истёкшие активные попытки в `lost`, пересчитывает
живые lease и обновляет совместимый cache `workers.active_count` derived
значением. Условные изменения состояния делают гонку `complete`, cancel и sweep
идемпотентной. Registration и `SweepExpired` также обслуживают ограниченный по
server time журнал сверок.

`internal/controlplane/store.go` использует derived count при регистрации,
чтении worker и выборе маршрута. `migrations/026_worker_capacity_reconciliations.sql`
хранит аудит расхождения (прежний cache, derived count, trigger и освобождённые
ghost slots); `internal/controlplane/metrics.go` и
`internal/protocol/types.go` отдают оконные показатели этого журнала.
`internal/worker/reconcile.go` завершает reconciliation manifest до повторной
регистрации, сохраняя fence от duplicate supervisor.

## Последовательный план

1. Оставить `workers.active_count` обратносуместимым cache и не принимать
   рекламируемый worker count как server authority.
2. В одной SQLite-транзакции обработать истёкшие lease, пересчитать active
   attempts и записать аудит только при реальном расхождении.
3. Вызывать путь сверки при registration, claim, terminal/cancel/heartbeat и
   periodic sweep; применять derived count в маршрутизации и ответах worker.
4. Хранить журнал migration 026 с индексами worker/time, ограничивать retention
   server time и отдавать reconciliation/ghost-slot метрики за окно.
5. Перед reconnect завершать manifest reconciliation; retained terminal state
   не превращать в активный слот и не создавать второй supervisor.
6. Закрепить stale-count, lost-complete/restart, гонки terminal/sweep, migration
   и метрики целевыми тестами.

## Критерии приёмки

1. При capacity=2 и искусственно stale `active_count=1`, когда живых attempts
   нет, две совместимые queued задачи получают две lease без рестарта worker.
2. Каждая непросроченная `preparing`/`running` попытка занимает ровно один
   слот; повторный claim или reconnect не запускает duplicate supervisor.
3. `succeeded`, `failed`, `cancelled` и `lost` освобождают слот ровно один раз,
   включая гонку completion и sweep и повтор HTTP-запроса.
4. После потери ответа completion и restart worker/control plane следующий
   registration, claim или sweep восстанавливает полную ёмкость; до истечения
   lease реальная работа остаётся зарезервированной.
5. Retained terminal worktree ограничивает repository capacity, но derived
   active count для него равен нулю.
6. API/метрики показывают derived active count и оконные reconciliation/ghost
   slots; upgrade 025→026 не требует ручной правки данных.

## Тест-план

- `internal/controlplane/store_test.go`: stale cache при capacity=2, два claim,
  terminal/sweep race, идемпотентный replay и граница lease.
- `internal/controlplane/metrics_test.go`: window и retention журнала, число
  reconciliation и ghost slots.
- `internal/controlplane/store_test.go`: upgrade 025→026 и rollback-read
  совместимого `active_count`.
- `internal/worker/worker_integration_test.go`: потерянный `/complete`, restart
  и reconnect заполняют все слоты; barrier подтверждает один live supervisor.
- Перед слиянием: целевой Go test и `git diff --check`; полный набор остаётся
  обязанностью этапа Verify.

## Риски и решения

- Гонка sweep/complete: состояние меняется условно в одной транзакции, а событие
  release публикует только победитель.
- Client clock: lease сверяется только с `Store.now()`, а не с часами worker.
- Агрессивный reset после restart: живой lease не сбрасывается до expiry;
  manifest/process identity защищают от повторного исполнения.
- Смешение retained и active: репозиторный handoff остаётся отдельным механизмом
  и не входит в derived worker count.
- Рост журнала: индексы и server-time retention ограничивают его без изменения
  текущей capacity семантики.

## Карточка работы

`knowledge/cards/CARD-0092-worker-active-capacity-self-recovery.md`

ГОТОВО-КОГДА: файл migrations/026_worker_capacity_reconciliations.sql
ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл internal/controlplane/store.go
ГОТОВО-КОГДА: файл internal/controlplane/metrics.go
ГОТОВО-КОГДА: файл internal/controlplane/store_test.go
ГОТОВО-КОГДА: файл internal/controlplane/metrics_test.go
ГОТОВО-КОГДА: файл internal/worker/registration.go
ГОТОВО-КОГДА: файл internal/worker/reconcile.go
ГОТОВО-КОГДА: файл internal/worker/worker_integration_test.go
ГОТОВО-КОГДА: команда go test ./internal/controlplane ./internal/worker -run '^(TestClaimReconcilesStaleCachedCapacityWithoutWorkerRestart|TestReconnectAfterLostCompletionRestoresEveryWorkerSlot)$' -count=1

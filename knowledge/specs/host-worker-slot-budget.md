# Спецификация: ёмкость слотов соответствует мощности машины

## Цель и влияние на владельца

Factory не выдаёт суммарно больше активных worker-слотов, чем логических CPU
видит сервер. Поэтому на восьмиядерной машине несколько worker-служб с локальной
ёмкостью по десять не создадут двадцать одновременно исполняемых задач: девятый
claim штатно останется пустым. Это сохраняет отзывчивость узла и делает
фактическую загрузку предсказуемой для владельца.

## Технический подход и реальные файлы

Контракт уже реализован в `internal/controlplane/state.go`: `Store.Claim` в
той же immediate SQLite-транзакции, где создаётся lease, считает непросроченные
attempts в состояниях `preparing` и `running` по всем worker. При достижении
предела он записывает идемпотентный пустой claim и не создаёт attempt.

`internal/controlplane/store.go` хранит предел в `hostMaxConcurrent`.
`Open` задаёт его как `max(1, runtime.NumCPU())`; `hostSlotLimit` даёт тот же
безопасный fallback прямым Store, а `OpenForTest` принимает явное положительное
значение. `internal/controlplane/store_test.go` покрывает заполнение бюджета,
replay, освобождение terminal/просроченным lease и гонку за последний слот.
Операторское различие между общим бюджетом машины и локальным
`max_concurrent` описано в `docs/worker.md` и `docs/local.md`.

В область не входят UI, миграции БД, wire-формат регистрации worker, изменение
диапазона локального `max_concurrent` и распределённый лимит для разных хостов.

## Последовательный план

1. Сохранить лимит узла в `Store` с безопасным значением по числу CPU для
   production и прямого создания Store.
2. Перед созданием нового attempt считать активные непросроченные lease всех
   worker в текущей SQLite-транзакции и вернуть пустой claim при заполнении.
3. Сохранить порядок: сначала идемпотентный replay существующего request, затем
   общий admission, чтобы повтор не блокировался заполненным бюджетом.
4. Проверить terminal-переход, истечение lease и конкурентные claim; пояснить
   операторам, что локальная ёмкость worker не является бюджетом машины.

## Критерии приёмки

1. При нескольких worker с локальной ёмкостью выше CPU первые `runtime.NumCPU()`
   claim суммарно создают attempts, а следующий возвращает пустой результат.
2. В счёт входят непросроченные `preparing` и `running`; terminal attempt и
   истёкший lease освобождают слот для следующего claim.
3. Повтор уже выданного request возвращает первоначальный attempt даже при
   заполненном общем лимите.
4. Два одновременных claim на последний слот дают ровно один новый attempt.
5. Прямой Store без явного лимита не блокирует выдачу и использует минимум один
   слот либо число логических CPU; тестовый явный лимит обязан быть положительным.
6. Документация отличает общий предел хоста от локального `max_concurrent`.

## Тест-план

- `TestClaimEnforcesHostMaxConcurrentAcrossWorkers`: общий предел, replay,
  terminal и expired lease.
- `TestConcurrentClaimsDoNotExceedHostCapacity`: один успех на последнем слоте.
- `TestDirectStoreClaimUsesDefaultHostCapacity` и
  `TestTestingHostSlotLimitIsExplicitAndProductionDefaultUnchanged`: безопасный
  fallback и явный тестовый лимит.
- Проверить формат документации через `git diff --check`.

## Риски и решения

- **Гонка последнего слота:** count и вставка attempt происходят в одной
  immediate SQLite-транзакции; это сериализует конкурирующие claim.
- **Потеря слота до запуска:** `preparing` учитывается сразу после выдачи lease.
- **Устаревший счётчик worker:** источником истины служат строки attempts, а не
  кэшированный `workers.active_count`.
- **Смешение ограничений:** локальный `max_concurrent` остаётся независимым
  пределом службы; общий бюджет относится ко всем worker одного control plane.
- **Удалённый fleet:** до появления host identity контракт применяется только к
  worker, обслуживаемым одним узлом и Store.

## Карточка работы

`knowledge/cards/CARD-0174-host-worker-slot-budget-specification.md`

Номер `0174` свободен в свежем `origin/main` и опубликованных ветках на момент
создания спецификации.

ГОТОВО-КОГДА: файл internal/controlplane/store.go
ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл internal/controlplane/store_test.go
ГОТОВО-КОГДА: файл docs/worker.md
ГОТОВО-КОГДА: файл docs/local.md
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run '^(TestClaimEnforcesHostMaxConcurrentAcrossWorkers|TestConcurrentClaimsDoNotExceedHostCapacity|TestDirectStoreClaimUsesDefaultHostCapacity|TestTestingHostSlotLimitIsExplicitAndProductionDefaultUnchanged)$' -count=1

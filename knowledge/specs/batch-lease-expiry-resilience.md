# Спецификация: активные работы не теряют lease синхронной пачкой

## Цель и влияние на владельца

Одновременно запущенные работы не должны разом переходить в `lost` с ошибкой
`lease expired` из-за краткой очереди запросов к control plane. Владелец
сохраняет результаты долгих агентских сессий и не перезапускает вручную целую
пачку задач после временной задержки SQLite или HTTP.

Защитный смысл lease сохраняется: если worker действительно не может связаться с
control plane до выданного сервером срока, supervisor останавливает runtime, а
sweep завершает attempt как `lost`. Задача не вводит автоматический retry, не
продлевает общий 30-секундный срок и не ослабляет запрет на двух владельцев одной
попытки.

## Технический подход и реальные файлы

Сейчас `internal/worker/attempt_lifecycle.go` создаёт отдельную heartbeat-
goroutine для каждого attempt. Все goroutine ждут один и тот же
`LeaseRenewInterval` (по умолчанию 10 секунд), а после ошибки — один и тот же
`LeaseRetryInterval` (2 секунды). Поэтому быстро заполненный пул синхронно
посылает renewals и синхронно повторяет их. Каждый запрос в
`internal/controlplane/state.go` открывает write-транзакцию, продлевает одну
аренду и дополнительно вызывает `reconcileWorkerCapacity`, хотя успешный
heartbeat не меняет множество активных attempts. Эта worker-wide сверка снова
ищет истёкшие попытки, считает все активные попытки и обновляет worker, усиливая
очередь SQLite именно в момент пачки renewals.

Реализация оставляет существующий endpoint
`PUT /api/v1/attempts/{attempt_id}/heartbeat` и формат протокола без изменений:

- worker вычисляет стабильную фазу из полного attempt ID и назначает обычный
  renewal в диапазоне от 70% до 100% `LeaseRenewInterval`; одновременно взятые
  attempts получают разные моменты запроса, но каждый начинает продление не
  позже прежних 10 секунд;
- повтор после transport/5xx ошибки получает такой же ограниченный разброс, а
  context запроса ограничивается минимумом из `requestTimeout` и оставшегося
  времени до lease deadline. Worker не начинает запрос, который уже не может
  завершиться до deadline, и по-прежнему останавливает attempt при
  `lease_not_owner` или исчерпанном сроке;
- после успешного ответа новый deadline сначала передаётся `attemptHandle` и
  supervisor, затем сохраняется в manifest. Медленная запись manifest больше не
  заставляет локальный supervisor жить по старому сроку; ошибка записи остаётся
  fail-closed, помечает worker нездоровым и останавливает attempt;
- `Store.Heartbeat` проверяет token/state/deadline, обновляет только
  `lease_expires_at` и фиксирует короткую транзакцию. Он не запускает
  `reconcileWorkerCapacity`: heartbeat не меняет active count. Истёкшие ghost-
  slots по-прежнему обрабатывают `Claim`, registration и `SweepExpired`, который
  запускается каждые пять секунд;
- документация фиксирует разнесённое продление и то, что server time остаётся
  единственным источником срока аренды.

Реальные файлы реализации: `internal/worker/attempt_lifecycle.go`, его unit- и
integration-тесты, `internal/controlplane/state.go`, store-регрессия, а также
описания контракта в `ARCHITECTURE.md` и `docs/worker.md`. Миграция, UI и новый
публичный endpoint не требуются.

## Последовательный план

1. Вынести чистый расчёт обычной и повторной задержки renewal по attempt ID;
   ограничить диапазоны и край lease deadline без зависимости от wall-clock в
   тестах.
2. Перевести `heartbeatAttempt` на рассчитанные задержки и deadline-aware request
   context; сохранить немедленную остановку при `lease_not_owner` и настоящем
   истечении lease.
3. После ответа сервера сначала обновлять deadline активного handle/supervisor,
   затем manifest; сохранить существующую реакцию на ошибку manifest.
4. Убрать worker-wide capacity reconciliation из успешного `Store.Heartbeat`;
   доказать, что heartbeat не завершает соседнюю expired attempt, а ближайший
   sweep делает это и освобождает слот.
5. Добавить детерминированную проверку пачки одинаково стартовавших attempts и
   integration-сценарий с краткой задержкой heartbeat: renewals распределены,
   все процессы остаются running, а затем корректно завершаются.
6. Обновить архитектурное и операторское описание, выполнить целевую Go-команду
   и `git diff --check`.

## Критерии приёмки

1. Для десяти attempts с одинаковыми исходными deadline расчёт даёт не менее
   трёх разных временных корзин renewal; ни один обычный renewal не назначен
   позже прежнего `LeaseRenewInterval` или после безопасной границы deadline.
2. Десять одновременно работающих attempts переживают искусственную краткую
   задержку обработчика heartbeat: ни один runtime не останавливается, все lease
   продлеваются и ни один attempt не получает `lost`/`lease expired`.
3. После временной transport/5xx ошибки попытки повторяют renewal с разнесённой
   задержкой в пределах оставшегося бюджета; `lease_not_owner` и исчерпанный
   deadline по-прежнему останавливают supervisor без позднего продления.
4. Успешный heartbeat продлевает только указанную активную attempt и не пишет
   capacity-reconciliation. Соседняя expired attempt остаётся до штатного sweep,
   после него ровно один раз становится `lost`, а execution — `failed`.
5. Новый deadline попадает в supervisor до потенциально медленной записи
   manifest. Ошибка manifest не маскируется и завершает attempt по существующему
   безопасному пути.
6. Endpoint, JSON-контракт, 30-секундный `LeaseDuration`, cancellation, terminal
   replay и явный operator retry остаются совместимыми; UI и схема БД не
   меняются.

## Тест-план

- В `internal/worker/attempt_lifecycle_test.go` table-driven тестирует чистый
  scheduler: стабильность по attempt ID, распределение десяти ID по корзинам,
  верхнюю границу обычной задержки и clamp около deadline.
- Там же проверить порядок успешного renewal через блокируемое manifest-
  сохранение: handle/supervisor уже видит новый deadline; ошибка сохранения
  вызывает прежний fail-closed исход.
- В `internal/worker/worker_integration_test.go` запустить пул из десяти fake
  runtimes через middleware, который на первом окне кратко задерживает heartbeat.
  Assert: запросы не приходят одной пачкой, все attempts остаются `running`,
  получают более поздний deadline и штатно завершаются.
- В `internal/controlplane/store_test.go` создать живую и истёкшую attempts одного
  worker. Heartbeat живой не должен менять соседнюю или писать trigger
  `heartbeat`; последующий `SweepExpired` должен один раз завершить истёкшую и
  сохранить корректный active count.
- Обязательная команда реализации запускает только новые регрессии двух пакетов;
  полный `go test ./...` остаётся единственному этапу Verify.

## Риски и решения

- Разброс может увеличить частоту renewals, если сделать его только отрицательным.
  Диапазон ограничен 70–100% текущего интервала; укороченная серверная транзакция
  компенсирует небольшое увеличение среднего числа запросов. Изменение интервала
  или `LeaseDuration` требует отдельного решения.
- Недетерминированный random сделает тест и расписание невоспроизводимыми.
  Используется стабильный hash полного attempt ID; token, короткий ID и секреты в
  лог или manifest не добавляются.
- Удаление reconciliation из heartbeat может задержать освобождение ghost-slot.
  Максимальная задержка остаётся пять секунд до sweeper, а пути Claim и
  registration продолжают сверку до admission. Тест проверяет обе границы.
- Локальные часы worker могут отличаться от server time. Worker не вычисляет
  новый абсолютный deadline, а использует timestamp ответа сервера; существующее
  fail-closed поведение при clock skew не расширяется этой работой.
- Слишком удобный grace period допустил бы прежнему владельцу ожить после
  передачи работы. Grace и позднее принятие heartbeat сознательно не вводятся:
  после server deadline token больше не владеет attempt.

## Карточка работы

`knowledge/cards/CARD-0096-batch-lease-expiry-resilience.md`

ГОТОВО-КОГДА: файл internal/worker/attempt_lifecycle.go
ГОТОВО-КОГДА: файл internal/worker/attempt_lifecycle_test.go
ГОТОВО-КОГДА: файл internal/worker/worker_integration_test.go
ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл internal/controlplane/store_test.go
ГОТОВО-КОГДА: файл ARCHITECTURE.md
ГОТОВО-КОГДА: файл docs/worker.md
ГОТОВО-КОГДА: команда go test -count=1 -run 'Test(ConcurrentAttemptsStaggerLeaseRenewalsUnderDelay|LeaseRenewalScheduleDispersesAttempts|HeartbeatDoesNotReconcileNeighboringExpiredLease)$' ./internal/worker ./internal/controlplane

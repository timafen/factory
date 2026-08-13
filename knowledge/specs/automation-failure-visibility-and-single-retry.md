# Спецификация: один автоматический повтор провалившегося запуска Automation

## Цель и влияние на владельца

Запуск Automation по расписанию или кнопке **Run now**, который завершился
`failed`, должен один раз автоматически вернуться в очередь. Владелец не теряет
разовый запуск из-за истёкшей lease или другого сбоя и на экране Automation
видит, что идёт повтор либо что запуск окончательно сорвался.

Повтор использует тот же execution, task, occurrence, `task_request_key` и
ссылку на Automation. Второй failure остаётся конечным и видимым. Работа не
добавляет retry для GitHub issue/pull-request Automations, обычных ручных задач
или `cancelled`, не переигрывает исторические провалы и не меняет cron,
timezone, lease либо политику ёмкости worker.

## Технический подход и реальные файлы

Сейчас `internal/controlplane/automation_runtime.go` создаёт для schedule-
occurrence ровно один task и execution, а затем переводит occurrence в
`dispatched`. Дальше runtime не наблюдает execution. Обычный failure фиксирует
`Store.CompleteAttempt` в `internal/controlplane/state.go`; истёкшую lease тот же
файл превращает в attempt `lost` и execution `failed` через `SweepExpired`.
Ручной `RetryExecution` уже возвращает тот же execution в `queued` и увеличивает
`retry_count`, но принимает также cancellation и не проверяет происхождение от
Automation.

Реализация добавляет общий транзакционный helper для двух путей terminal
failure. После фиксации attempt helper делает условный атомарный переход
execution `failed → queued`, только если одновременно:

- task связан с `automation_occurrences.state = 'dispatched'` и типом
  `schedule`, а kind равен `scheduled` или `run_now`;
- Automation, её Workflow и Repository всё ещё включены;
- `retry_count = 0`, cancellation не запрошена;
- закреплённый `assigned_worker_id` по тем же фактическим правилам допуска
  route/repository/runtime остаётся online, healthy и доступен. Worker не
  переназначается, динамическая repository reservation не восстанавливается
  автоматически.

Успех обновляет только тот же execution (`state = 'queued'`,
`retry_count = 1`, `cancellation_requested = 0`) и diagnostic существующего
occurrence. Никаких INSERT task/execution/occurrence нет. Если условие не
выполнено из-за второго failure, cancellation, disablement или недоступности
worker, execution остаётся terminal, а occurrence получает стабильный код
причины: retry исчерпан, отключён или worker недоступен. Обновление execution и
diagnostic коммитятся вместе с terminal attempt: повтор completion, повторный
sweep и запуск нового процесса не могут поставить работу в очередь второй раз.

`internal/protocol/types.go` расширяет `AutomationTaskSummary` полями
`retry_count` и owner-facing `retry_status` (`queued`, `running`, `succeeded`,
`final_failed`, `skipped_disabled`, `skipped_worker_unavailable`; поле
отсутствует для старых и нецелевых запусков). `internal/controlplane/automations.go`
читает retry count и сохранённый diagnostic, не вычисляя историю по времени.
Значение `Automation.health` не становится `healthy` только потому, что retry
поставлен в очередь: карточка и список используют состояние latest run.

Экранная часть интегрируется после/поверх CARD-0123: не создаётся второй экран,
новая панель или параллельная модель run history. В существующих строках Run
`web/src/Automations.tsx` показывает понятные метки **Retry queued**,
**Retry running** и **Failed after retry**; при запрете повтора — **Failed —
Automation disabled** или **Failed — worker unavailable**. Голые ID и внутренние
коды не показываются. `web/src/types.ts`, `web/src/test/fixtures.ts` и
`web/src/App.test.tsx` получают совместимые поля, fixtures и проверки списка и
detail. Если CARD-0123 ещё не в `main` при Implement, сначала берётся её
опубликованный UI-контракт и разрешаются пересечения без копирования её экрана.

## Последовательный план

1. Вынести общий SQL/helper допуска одного automatic retry и применить его в
   транзакциях `CompleteAttempt` и `SweepExpired` после подтверждённого перехода
   execution в `failed`.
2. Закрепить compare-and-set по `state = 'failed' AND retry_count = 0`, связь с
   schedule-occurrence и отсутствие INSERT; записывать durable diagnostic для
   queued retry и каждой причины окончательного failure.
3. Переиспользовать правила доступности закреплённого worker без его замены и
   без автоматического восстановления repository reservation; cancellation и
   отключённые Automation/Workflow/Repository оставить terminal.
4. Расширить Automation occurrence projection retry count/status и сохранить
   обратную совместимость JSON для запусков без автоматического повтора.
5. Поверх CARD-0123 добавить метки retry/final failure в существующие список и
   detail, не подменяя failure состоянием Automation health.
6. Добавить lifecycle/idempotency Go-тесты и UI-тесты, затем выполнить целевые
   команды и `git diff --check`.

## Критерии приёмки

1. Первый `failed` scheduled и Run now execution атомарно становится `queued`,
   а `retry_count` — `1`; новый attempt при claim имеет следующий номер.
2. После повтора остаются прежними ID execution/task/occurrence, task
   `request_key`, `task_id_snapshot`, Automation ID и число строк в этих
   таблицах.
3. Второй `failed` при `retry_count = 1` остаётся `failed`, получает
   `final_failed` и не создаёт третью попытку.
4. `cancelled` не запускает automatic retry. Failure при отключённой
   Automation, Workflow или Repository остаётся конечным с понятной причиной.
5. Offline/unhealthy worker, несовместимый runtime или недоступная закреплённая
   repository reservation не приводят к retry либо переназначению worker;
   причина видна владельцу.
6. Повтор terminal completion, второй sweep той же lease и открытие Store на той
   же БД после server restart не меняют `retry_count = 1` и не создают записи.
7. GitHub issue/pull-request Automations и обычные задачи сохраняют прежнюю
   retry-семантику; успешный первый запуск не повторяется.
8. Список и detail Automation различают queued/running retry и окончательный
   failure; final failure не выглядит healthy и не требует чтения ID или
   внутренних diagnostic-кодов.

## Тест-план

- В `internal/controlplane/schedule_automations_test.go` добавить сценарии для
  scheduled и Run now: first failure → тот же queued execution с
  `retry_count=1` → claim второго attempt → second failure без retry. Сравнить
  все identity/request key и количества строк.
- Там же проверить успешный retry и JSON projection, cancellation, disablement
  Automation/Workflow/Repository, offline/unhealthy worker, несовместимый
  runtime и недоступную frozen repository assignment.
- Отдельно провести failure через `SweepExpired`, повторить sweep/completion и
  переоткрыть Store на том же файле БД: после restart остаётся одна очередь и
  два attempts максимум.
- Регрессией подтвердить отсутствие automatic retry у GitHub-triggered
  occurrence и обычного task, а также неизменность ручного `RetryExecution`.
- В `web/src/App.test.tsx` проверить list/detail для Retry queued, Retry running,
  Failed after retry и двух skipped-причин; рядом сохранить тест обычного
  `Failed` из CARD-0123 и отсутствие ложного healthy.
- Обязательная целевая команда:
  `go test ./internal/controlplane -run 'TestScheduleAutomationFailedExecutionRetriesOnceAndIsIdempotent' -count=1`.
- Дополнительные команды Implement:
  `go test ./internal/controlplane -run 'Test.*(Automation|Schedule)' -count=1`
  и `npm --prefix web test -- --run src/App.test.tsx`.

## Риски и решения

- **Гонка failure/disable/restart.** Все eligibility-проверки, CAS, diagnostic и
  terminal attempt входят в одну SQLite-транзакцию; фонового in-memory флага
  нет.
- **Retry после потери worker.** Повтор сохраняет worker affinity и требует
  текущего полного допуска. Недоступность — конечное наблюдаемое состояние, а
  не бесконечное ожидание или скрытое переназначение.
- **Повторный HTTP completion и sweep.** `retry_count = 0` и проверка реально
  изменённого terminal перехода дают один durable winner.
- **Смешение health и run state.** Health продолжает описывать проверку
  Automation; UI явно отдаёт приоритет latest run retry/final-failure.
- **Параллельная CARD-0123.** Реализация расширяет её существующий экранный
  контракт и тесты, не копирует компоненты. Пересечения разрешаются при Implement
  после получения опубликованного commit CARD-0123.
- **Diagnostic как машинный контракт.** Сервер отдаёт типизированный
  `retry_status`, UI маппит его на текст; сырой diagnostic остаётся для
  расследования и не выводится как владелец-видимая формулировка.

## Карточка работы

Текущая работа ведётся отдельно в
`knowledge/cards/CARD-0124-automation-failure-visibility-and-single-retry.md`.
CARD-0123 остаётся зависимой поставкой owner-facing экрана; область CARD-0124 —
автоматический retry, его durable статус и интеграция меток.

ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл internal/controlplane/automation_runtime.go
ГОТОВО-КОГДА: файл internal/controlplane/schedule_automations_test.go
ГОТОВО-КОГДА: файл internal/controlplane/automations.go
ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл web/src/types.ts
ГОТОВО-КОГДА: файл web/src/test/fixtures.ts
ГОТОВО-КОГДА: файл web/src/Automations.tsx
ГОТОВО-КОГДА: файл web/src/App.test.tsx
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run 'TestScheduleAutomationFailedExecutionRetriesOnceAndIsIdempotent' -count=1

# Спецификация: честная цена дублей, отмен и незавершённых конвейеров

## Цель и влияние на владельца

Владелец должен видеть не только `failed/cancelled`, а доказуемую причину
исхода и стоимость уже потраченного Codex. Обзор показывает отдельные суммы и
количества для `owner_cancel`, `system_duplicate`, `review_return`,
`verify_return`, `undelivered` и `unknown`; старые записи не классифицируются по
заголовку. Каждая новая сумма расходов привязана к `work_id`, поэтому один
конвейер не теряет цену этапа и не получает цену чужой работы.

## Технический подход и реальные файлы

Текущее состояние: `executions` в `migrations/001_controlplane.sql` хранит
только состояние и `cancellation_requested`; `CancelTask` в
`internal/controlplane/state.go` не принимает причину. `tasks.work_id` и
`correction_kind` уже добавлены миграцией 027, но `internal/protocol/types.go`
и `internal/controlplane/metrics.go` не отдают классификацию или стоимость.

1. Создать `migrations/028_outcome_cost_attribution.sql`: добавить nullable
   `executions.outcome_code` (для старых строк — `unknown`) и таблицу
   `codex_usage_costs` с integer micro-USD, `work_id`, task/execution/attempt
   ссылками, временем и уникальным источником события. Индексы покрывают
   `(work_id, recorded_at)` и период метрик. Доллары вычисляются только из
   micro-USD, без float в хранении.
2. В `internal/protocol/types.go` описать закрытый набор кодов исхода,
   запрос отмены с обязательным `outcome_code=owner_cancel`, запись стоимости
   и расширенные `MetricsSummary`: разрез исходов, `wasted_cost_usd`,
   `unknown_cost_usd` и стоимость по коду/work. Новая запись расхода должна
   отклоняться без `work_id` или с неподтверждённой ссылкой; старые orphaned
   расходы попадают только в `unknown`.
3. В `internal/controlplane/state.go` и обработчиках отмены в
   `internal/controlplane/http.go` принимать и транзакционно сохранять явную
   причину. Запретить эвристики по title/error. Пути создания continuation
   используют уже валидированный `correction_kind` и одновременно записывают
   соответствующий outcome; duplicate и undelivered получают явный вызов
   источника, а не догадку из текста. Историческая backfill-операция меняет
   только NULL на `unknown`.
4. В `internal/controlplane/metrics.go` считать только расходы внутри окна по
   `recorded_at`, группировать по `work_id` и коду, и отдельно показывать
   unknown. Не включать активные `queued/preparing/running` в completed,
   но показывать их как незавершённые; `undelivered` считается расходом
   незавершённого конвейера только после явной фиксации исхода.
5. Добавить/обновить `internal/controlplane/metrics_test.go`,
   `internal/controlplane/http_test.go`, `internal/controlplane/store_test.go`
   и при необходимости `internal/controlplane/work_resume_http_test.go`:
   проверить миграцию, валидацию, идемпотентность cost event, отмену с причиной,
   отсутствие title-эвристик и раздельную агрегацию работы.

## Последовательный план

1. Зафиксировать контракт кодов, единицы стоимости и переходы состояний.
2. Добавить миграцию и API-модели с безопасным чтением старых строк.
3. Подключить явные записи исходов ко всем новым отменам, возвратам, дублям и
   недоставленным продолжениям.
4. Подключить приём/идемпотентность расходов и расчёт метрик.
5. Написать целевые регрессии, прогнать обязательную команду и проверить diff.

## Критерии приёмки

- Новая отмена без явной причины отклоняется; `owner_cancel` сохраняется без
  анализа названия задачи.
- Новые duplicate/review/verify/undelivered создаются только с одноимённым
  кодом; старые неподтверждённые строки видны как `unknown`.
- Один cost event нельзя посчитать дважды; каждая принятая запись имеет
  `work_id`, а суммы разных работ не смешиваются.
- Метрики отдельно показывают количество и USD для пяти кодов и unknown,
  включая расходы отменённых, дублей и недоставленных конвейеров.
- Активные и действительно незавершённые состояния не маскируются под
  `failed`; completed и success rate остаются совместимыми с существующим API.
- Существующие клиенты без новых полей продолжают читать metrics; старые
  базы проходят миграцию без догадки о причинах.

## Тест-план

- `go test ./internal/controlplane -run 'Test(Metrics|Cancel|TaskProvenance|WorkResume|Store).*' -count=1` — миграция, API, исходы, idempotency и агрегация.
- Целевой fixture создаёт две работы с одинаковой суммой, duplicate и owner
  cancel, затем проверяет независимые totals, unknown history и один event.
- HTTP-тест проверяет отказ пустого тела отмены и JSON-контракт метрик.
- `git diff --check` и `git diff --name-only origin/main...HEAD` проверяют
  документационную поставку; полный набор проекта для этапа спецификации не
  запускается.

## Риски и решения

- Причину невозможно восстановить из старых title/error — сохранять `unknown`
  и отдельную стоимость, не делать backfill-эвристику.
- Повторная доставка стоимости завысит USD — обязательный idempotency key и
  unique constraint на источнике события.
- Несовместимые часы/float исказят цену — micro-USD integer и server timestamp.
- Незавершённый pipeline может быть ещё жив — `undelivered` выставляет только
  владелец/системный переход после подтверждённой границы доставки.
- Удалённая ветка triage `factory/dcbfac88-0a8-dac39709-59c` не опубликована;
  спецификация основана на доступном свежем `origin/main` и отчёте triage.

## Карточка работы

`knowledge/cards/CARD-0090-metrics-outcome-cost-attribution.md` — отдельная
карточка текущей работы; CARD-0059 и CARD-0038 не изменяются.

ГОТОВО-КОГДА: файл migrations/028_outcome_cost_attribution.sql
ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл internal/controlplane/http.go
ГОТОВО-КОГДА: файл internal/controlplane/metrics.go
ГОТОВО-КОГДА: файл internal/controlplane/metrics_test.go
ГОТОВО-КОГДА: файл internal/controlplane/http_test.go
ГОТОВО-КОГДА: файл internal/controlplane/store_test.go
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run 'Test(Metrics|Cancel|TaskProvenance|WorkResume|Store).*' -count=1

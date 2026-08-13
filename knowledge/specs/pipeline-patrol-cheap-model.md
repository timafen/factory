# Патруль ходит на дешёвой модели

## Цель и влияние на владельца

Закрепить ежечасный pipeline patrol за точным Codex model ID
`gpt-5.6-terra`, чтобы обычные проверки не расходовали `gpt-5.6-sol`. Переход
принимается только после контрольных суток: на одинаковом входном наборе
`terra` должна сохранить не менее 90% подтверждённых полезных находок, а её
доля ложных срабатываний может быть выше `sol` не более чем на 5 процентных
пунктов. При нарушении любого порога патруль остаётся на `gpt-5.6-sol` и
результат явно объясняется владельцу.

## Технический подход и реальные файлы

Существующая schedule Automation остаётся единственным ежечасным источником
запуска: `internal/controlplane/pipeline_patrol.go` добавляет в неё модельную
политику, а `internal/controlplane/schedule_runtime.go` переносит её в snapshot
Occurrence и Task. Добавить в Task/Claim явный необязательный `model_id`,
валидируемый для Codex; для патруля значение всегда `gpt-5.6-terra`, для
остальных задач сохраняется текущее поведение. Это требует
`migrations/029_pipeline_patrol_model.sql`, `internal/protocol/types.go`,
`internal/controlplane/automation_runtime.go` и соответствующих store/API
проверок.

`internal/worker/supervisor.go` должен передавать model ID в `codex exec -m`
и сохранять фактически запущенную модель в событиях/результате попытки.
`internal/worker/prompt_test.go` и новый worker integration test проверят, что
патруль не стартует без точного ID и что обычная задача не получает override.
`internal/controlplane/pipeline_patrol_test.go` и
`internal/controlplane/schedule_automations_test.go` проверят snapshot,
идемпотентность и отсутствие подмены модели при повторной доставке.

Контроль качества реализовать в `pilot/pilot.py`: парный evaluator подаёт один
и тот же детерминированный вход `terra` и `sol`, нормализует находки по
стабильному ключу, принимает подтверждение человека/эталона и считает
`useful_retention = confirmed_terra / confirmed_sol` и
`false_positive_delta_pp = fp_terra * 100 - fp_sol * 100`. Сводка и решение
хранятся в отдельном audit JSON; `pilot/test_pilot.py` фиксирует одинаковый
input hash, расчёт порогов и fail-closed fallback. Не менять общий
`brain_chain`: он не является доказательством маршрутизации патруля.

## Последовательный план

1. Добавить миграцию и поле model ID в occurrence/task/execution snapshot с
   обратной совместимостью для старых задач.
2. Передать override через dispatch, claim и Codex supervisor; запретить
   произвольные модели и оставить обычные задачи без изменения.
3. Зафиксировать `gpt-5.6-terra` в provisioned patrol, сохраняя cron,
   timezone, request key и idempotent replay.
4. Добавить pair-run evaluator за контрольные сутки с одинаковым входом,
   нормализацией находок и ручным подтверждением эталона.
5. Включать terra только при обоих порогах; иначе записывать отказ и оставлять
   patrol на `gpt-5.6-sol`.

## Критерии приёмки

- Каждый новый ежечасный patrol Task содержит `model_id=gpt-5.6-terra` в
  durable snapshot; старый или повторно доставленный run не теряет значение.
- Codex получает ровно `-m gpt-5.6-terra`; не-патрульная задача сохраняет
  прежний вызов без override, а неизвестный model ID отклоняется до запуска.
- Pair-run использует одинаковый нормализованный input hash и полный
  контрольный интервал 24 часа; каждая находка имеет verdict полезна/ложна.
- Переключение разрешено только при retention >= 0.90 и
  false-positive delta <= 5.0 percentage points; иначе effective model остаётся
  `gpt-5.6-sol`.
- Повторный provision не дублирует инструкции, не меняет расписание и не
  создаёт второй audit decision; отсутствие эталонных verdicts блокирует
  переключение.

## План тестирования

- `go test ./internal/controlplane -run 'Test.*(Schedule|Patrol)'` — текущий
  целевой regression gate для schedule/patrol.
- `go test ./internal/controlplane -run 'Test.*(Patrol|Schedule|Model)'`:
  миграция, CAS/idempotency, snapshot и dispatch после реализации.
- `go test ./internal/worker -run 'Test.*(Model|Prompt|Codex)'`:
  точный `-m`, отсутствие override и фактический model event.
- `python3 -m unittest pilot.test_pilot.PatrolModelEvaluationTests`:
  одинаковый input, метрики 90%/5 п.п., граничные значения и fail-closed.
- Отдельно выполнить контрольный 24-часовой pair-run на зафиксированном
  наборе и приложить его audit summary; симуляция не заменяет этот gate.

## Риски и решения

- Сейчас runtime выбирается worker-wide, а model ID не входит в Task/Claim;
  поэтому одной правкой Automation нельзя доказать маршрут. Поле проходит
  весь snapshot/claim путь и логируется фактическим запуском.
- Смешение разных входов исказит сравнение; сохранять input hash и версии
  workflow/repository в audit, а несовпадение делать блокирующим.
- Подтверждение находок субъективно; verdict обязан быть явным и воспроизводимым
  по ключу находки, неизвестный verdict не считается полезным.
- `terra` может быть недоступна по квоте; это operational failure, не повод
  считать тест пройденным: patrol временно остаётся на `sol` с диагностикой.
- Предыдущая ветка `factory/d1d7fdb6-725-86471950-911` отсутствует на origin,
  поэтому спецификация основана на свежем `origin/main` и отчёте Triage.

## Карточка работы

`knowledge/cards/CARD-0097-pipeline-patrol-cheap-model.md`

ГОТОВО-КОГДА: файл migrations/029_pipeline_patrol_model.sql
ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл internal/controlplane/pipeline_patrol.go
ГОТОВО-КОГДА: файл internal/controlplane/schedule_runtime.go
ГОТОВО-КОГДА: файл internal/controlplane/automation_runtime.go
ГОТОВО-КОГДА: файл internal/worker/supervisor.go
ГОТОВО-КОГДА: файл internal/controlplane/pipeline_patrol_test.go
ГОТОВО-КОГДА: файл internal/controlplane/schedule_automations_test.go
ГОТОВО-КОГДА: файл internal/worker/prompt_test.go
ГОТОВО-КОГДА: файл internal/worker/model_override_test.go
ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run 'Test.*(Schedule|Patrol)'

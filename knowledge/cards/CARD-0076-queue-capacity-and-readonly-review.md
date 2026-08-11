Implementation commit: d5c1b0419c8540b07a8be071d0b9e035d336b88d — переназначения считаются по времени событий, а `NOT READY` повторно ставит Review в очередь.

# CARD-0076 — Очередь использует свободных совместимых исполнителей

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/07ad4173-33f-c7c279e1-e50`.
- Implementation commit: `d5c1b0419c8540b07a8be071d0b9e035d336b88d` — события
  переназначения считаются по времени, а `NOT READY` повторно ставит Review в очередь.
- What changed: `025` хранит фактические события переназначения; worker передаёт
  read-only `NOT READY` структурированно, а control plane атомарно возвращает execution в `queued`.
- Evidence: `just check` (после `npm ci` продолжены только не выполненные UI/tooling/launcher
  части) → PASS: Go, анализаторы, 155 UI-тестов, три бинарника и launcher; production UI build → PASS.
- One next action: выполнить human merge ветки в `main`.

## LOG

### 2026-08-11 — Implement

Для совместимости с `main` миграция перенумерована с `023` на `024`, а карточка
перенесена с `CARD-0070` на `CARD-0076`. Ссылка в спецификации приведена к новому
имени. Логика Go/React не менялась; `aa6160e3e6caef5d657c1abc56aa795d2861acd8`
остаётся реализационным коммитом-предком с изменениями вне `knowledge/cards`.

### 2026-08-11 — Implement

Убран жёсткий фильтр очереди по первоначальному worker: claim проверяет runtime,
advertised repository, общую и retained capacity запрашивающего worker, затем
атомарно меняет назначение и создаёт единственный attempt. Конкурентный тест
подтвердил один claim без остановки writer; несовместимость остаётся временным
пустым ответом и успешно перепроверяется после регистрации репозитория.

Review получил версионируемый `read_only`, snapshot в Task/Claim и обязательное
правило committed snapshot / non-blocking writer / `NOT READY`. На Обзоре виден
24-часовой счётчик переназначений. Полный Go-набор, 155 UI-тестов, lint,
typecheck, UI build и сборка трёх бинарников завершились успешно.

### 2026-08-11 — Implement

Метрика `queue_reassignments` переведена с накопительного счётчика execution на
журнал событий с `reassigned_at`, поэтому последующее обновление execution не
переносит старое событие в новое окно. `NOT READY` read-only Review теперь
передаётся worker как `disposition:not_ready`; control plane завершает попытку и
повторно ставит execution в очередь одной транзакцией. Go- и UI-проверки прошли.

### 2026-08-11 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Upgrade `023→024→025` | `just check` / `TestSpecificationPublishesDocumentsMigrationInstallsExactRevision` и store-тесты | PASS: база через `023` открылась с применёнными `024` и `025`; новые поля и журнал используются тестами |
| Старые события не повторяются в `reassigned_at` | `TestMetricsCountQueueReassignmentsByEventTime` | PASS: старое событие осталось вне окна 24h после нового `updated_at` execution |
| Structured `NOT READY` ставит тот же execution в очередь ровно один раз | `TestReadOnlyNotReadyIsRequeuedWithoutDuplicateAttempt` | PASS: тот же task завершился после двух attempts — один failed `NOT READY`, один succeeded |
| Свободный совместимый worker без дубля | `TestCompatibleIdleWorkerClaimsQueuedAssignment`, `TestCompatibleWorkersClaimOnceWhileWriterContinues` | PASS: единственный claim/attempt, writer продолжил работу |
| UI и сборка | `just ui-check`, `just test-tooling` | PASS: lint, typecheck, 155 тестов, production UI и три Go-бинарника |

Трёхточечный `git diff origin/main...HEAD` непустой и проходит `git diff --check`.
Implementation commit `d5c1b0419c8540b07a8be071d0b9e035d336b88d` существует, является предком
ветки, не совпадает с карточным tip и меняет код и миграцию вне `knowledge/cards/`.

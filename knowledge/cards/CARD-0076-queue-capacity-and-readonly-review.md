Implementation commit: 09dcb88bdaeda50918189ca7a79a027d1985597a — пачка завершённых переходов следует числу рабочих слотов.

# CARD-0076 — Очередь использует свободных совместимых исполнителей

## HEAD

- Status: Implemented and targeted tests pass — awaiting Verify.
- Branch: `factory/7b896d6e-94c-fcc12d96-478`.
- Implementation commit: `09dcb88bdaeda50918189ca7a79a027d1985597a` — размер пачки
  завершённых handoff связан с общим лимитом параллельных работ.
- What changed: Pilot за один цикл может заполнить все четыре поддерживаемых слота;
  тест не даст лимитам разойтись при следующем изменении capacity.
- Evidence: `AdaptivePollingTests` → PASS (30 тестов); `just build` → PASS;
  `just check` → анализаторы PASS, общий Go-тест остановлен средой по SIGTERM.
- One next action: на Verify повторить полный `just check` без минутного ограничения среды.

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

### 2026-08-15 — Implement

Размер пачки завершённых переходов привязан к `MAX_PARALLEL_WORKS`, чтобы Pilot
не оставлял свободные слоты при изменении поддерживаемой параллельности. Все 30
`AdaptivePollingTests` и сборка прошли. Единственный `just check` прошёл vet,
govulncheck и staticcheck, затем был остановлен средой по SIGTERM на `go test ./...`.

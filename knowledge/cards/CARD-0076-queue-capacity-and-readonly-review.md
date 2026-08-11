Implementation commit: d5c1b0419c8540b07a8be071d0b9e035d336b88d — переназначения считаются по времени событий, а `NOT READY` повторно ставит Review в очередь.

# CARD-0076 — Очередь использует свободных совместимых исполнителей

## HEAD

- Status: Implemented and tested — awaiting Review.
- Branch: `factory/07ad4173-33f-c7c279e1-e50`.
- Implementation commit: `d5c1b0419c8540b07a8be071d0b9e035d336b88d` — события
  переназначения считаются по времени, а `NOT READY` повторно ставит Review в очередь.
- What changed: `025` хранит фактические события переназначения; worker передаёт
  read-only `NOT READY` структурированно, а control plane атомарно возвращает execution в `queued`.
- Evidence: `go test ./...` → PASS; `npm --prefix web run lint/typecheck/test/build` → PASS;
  `git rebase origin/main` → up to date.
- One next action: выполнить Review реализации и миграций `024`/`025`.

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

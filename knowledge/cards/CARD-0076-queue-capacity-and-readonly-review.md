Implementation commit: aa6160e3e6caef5d657c1abc56aa795d2861acd8 — свободный совместимый worker атомарно забирает очередь, а Review работает по read-only snapshot.

# CARD-0076 — Очередь использует свободных совместимых исполнителей

## HEAD

- Status: Implemented and tested — awaiting Review.
- Branch: `factory/651e7e80-9ba-e10a6847-9b9`.
- Implementation commit: `aa6160e3e6caef5d657c1abc56aa795d2861acd8`.
- What changed: claim переносит queued execution на совместимый worker в одной
  транзакции; поставка перенесена на миграцию `024` без изменения логики.
- Evidence: `git diff --cached --check` → PASS; поиск `023_queue_reassignment`
  вне истории → нет ссылок; `aa6160e…` — предок текущей ветки и меняет код.
- One next action: выполнить Review реализационного коммита и миграции `024`.

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

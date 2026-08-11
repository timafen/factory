Implementation commit: aa6160e3e6caef5d657c1abc56aa795d2861acd8 — свободный совместимый worker атомарно забирает очередь, а Review работает по read-only snapshot.

# CARD-0070 — Очередь использует свободных совместимых исполнителей

## HEAD

- Status: Implemented and tested — awaiting Review.
- Branch: `factory/1b25edf5-173-b9b9b6cf-e00`.
- Implementation commit: `aa6160e3e6caef5d657c1abc56aa795d2861acd8`.
- What changed: claim переносит queued execution на совместимый worker в одной
  транзакции; Workflow/Task сохраняют read-only snapshot для Review.
- Evidence: `go test -timeout 5m ./...` → PASS; `npm test` → 14 files,
  155 tests PASS; `npm run lint`, `npm run typecheck`, `npm run build` → PASS;
  `just build` → три бинарника собраны.
- One next action: выполнить Review реализационного коммита и миграции.

## LOG

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

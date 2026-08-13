# CARD-0101 — «В работе прямо сейчас» только для начатых попыток

Implementation commit: 507abf5bacde7075cd09b137a0623d78086e9aa4 — существующая реализация экрана «Работа», для которой эта спецификация уточняет границу активного состояния.

## HEAD

- Status: Specification ready — awaiting implementation.
- Branch: factory/22052306-790-e9db5025-ff2
- Specification: `knowledge/specs/active-work-requires-started-at.md`
- Scope: только отличение `started_at = NULL` от фактически начатой попытки в server read-модели, Work и Overview.
- Out of scope: lifecycle, назначение исполнителей, capacity и производительность.

## LOG

### 2026-08-12 — Specification

Фактический код подтверждает дефект: `internal/controlplane/store.go:scanTask`
преобразует `preparing` в `running`, а `web/src/Work.tsx` считает `running`
активным. `StartAttempt` в `internal/controlplane/state.go` записывает
`started_at` только при реальном старте. Зафиксировано решение передавать дату
текущей попытки в задаче и использовать её как единственный признак активной
работы; очередь и активный раздел должны иметь независимые регрессии.

Проверено по свежему `origin/main`: путь карточки свободен; опубликованные
refs не содержат CARD-0101. Реализация и UI на этом этапе не изменялись.

## Готовность к реализации

- Server: `internal/protocol/types.go`, `internal/controlplane/store.go` и
  целевая серверная регрессия.
- Web: `web/src/types.ts`, `web/src/Work.tsx`, `web/src/Overview.tsx` и
  перечисленные тесты.
- Обязательная проверка: `go test ./internal/controlplane/...`.

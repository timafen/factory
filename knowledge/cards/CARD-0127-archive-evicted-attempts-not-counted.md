# CARD-0127 — Архивные вытесненные попытки не занимают лимит

Implementation commit: 5773ad1f568aa15b4086178f958ff33000bed08c — зафиксирован исходный control-plane контекст; продуктовый код на этапе Specification не изменяется

Status: Specification — ожидает Implement
Branch: factory/f760d893-00d-5bdcf4a9-e04
Scope: `internal/controlplane/state.go`, `internal/controlplane/store.go`, `internal/controlplane/store_test.go`

Вытесненная terminal-попытка должна оставаться в истории задачи, но после
подтверждения передачи capacity не должна занимать лимит retained capacity.
Реально сохранённые worktree и неподтверждённые terminal-переходы продолжают
резервировать место до штатного cleanup/registration.

Проверяемый результат: при заполненном почти до лимита репозитории завершённая
и подтверждённо вытесненная попытка остаётся видимой в API, а следующая задача
успешно маршрутизируется и получает claim; активная и неподтверждённая запись
по-прежнему блокируют переполнение.

Связанная спецификация: `knowledge/specs/archive-evicted-attempts-not-counted.md`.

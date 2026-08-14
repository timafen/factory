# CARD-0127 — Архивные вытесненные попытки не занимают лимит

Implementation commit: ef5728919a2542ad293f3f5731529a64c5d09f34 — добавлена регрессия архивной вытесненной попытки и её освобождения capacity

## HEAD

Status: Verified PASS — awaiting human merge
Branch: factory/fdc19e80-7c6-d8a9e288-3e5
Implementation commit: ef5728919a2542ad293f3f5731529a64c5d09f34
Evidence: полный набор `go test ./...` и целевой regression test прошли; pinned comparison: base `051316a3c410aeb1e1d9c0e44ab7753fdc4ae76a` → candidate `f32d47e19894da49b5de493323c88a015133b603`.
Next action: human merge candidate into main.

## LOG

### 2026-08-14 — Implement

Добавлен тест архивной вытесненной попытки: запись остаётся в API-истории, подтверждается без изменения retained_count и не препятствует route следующей задачи. Целевой набор controlplane прошёл.

### 2026-08-14 — Implement transfer

Готовая реализация опубликована в требуемой ветке; карточка привязана к ней. Целевые проверки controlplane прошли.

### 2026-08-14 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Архивная попытка остаётся в истории с terminal-данными | `ArchivedEvictedAttemptDoesNotConsumeRepositoryCapacity` | PASS |
| Освобождённая capacity допускает следующий claim/route | тот же тест + `RoutedTaskExcludesWorkersWithoutRepositoryCapacity` | PASS |
| Активные, retained и неподтверждённые terminal-попытки блокируют переполнение | `TerminalAttemptReservesRetainedHeadroomUntilRegistration` | PASS |
| Claim, route, options и readiness используют единый derived retention use | полный `go test ./...` | PASS |
| UI, wire-формат и удаление истории не изменены | pinned diff files + `git diff --check` | PASS |

Полный набор: `go test ./...` → PASS (exit 0). Целевой набор с `-count=1` → PASS. Рабочее дерево проверено без отладочных или лишних файлов.

### 2026-08-14 — Specification

Вытесненная terminal-попытка должна оставаться в истории задачи, но после
подтверждения передачи capacity не должна занимать лимит retained capacity.
Реально сохранённые worktree и неподтверждённые terminal-переходы продолжают
резервировать место до штатного cleanup/registration.

Проверяемый результат: при заполненном почти до лимита репозитории завершённая
и подтверждённо вытесненная попытка остаётся видимой в API, а следующая задача
успешно маршрутизируется и получает claim; активная и неподтверждённая запись
по-прежнему блокируют переполнение.

Связанная спецификация: `knowledge/specs/archive-evicted-attempts-not-counted.md`.

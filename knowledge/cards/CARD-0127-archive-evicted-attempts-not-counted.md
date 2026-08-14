# CARD-0127 — Архивные вытесненные попытки не занимают лимит

Implementation commit: ef5728919a2542ad293f3f5731529a64c5d09f34 — добавлена регрессия архивной вытесненной попытки и её освобождения capacity

## HEAD

Status: Implement — готово к проверке
Branch: factory/7bda4a13-6fb-a211739d-182
What changed: архивная terminal-попытка сохраняет state/result/error в истории после подтверждения вытеснения.
What changed: readiness, варианты репозитория и route снова допускают задачу при освобождённом retained capacity.
Evidence: `go test ./internal/controlplane -run 'Test(RoutedTaskExcludesWorkersWithoutRepositoryCapacity|TerminalAttemptReservesRetainedHeadroomUntilRegistration|ArchivedEvictedAttemptDoesNotConsumeRepositoryCapacity)$'` → PASS.
Next action: проверить изменение на этапе Verify.

## LOG

### 2026-08-14 — Implement

Добавлен тест архивной вытесненной попытки: запись остаётся в API-истории, подтверждается без изменения retained_count и не препятствует route следующей задачи. Целевой набор controlplane прошёл.

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

Implementation commit: 7b0e963d2f8ae6c6d80570ed9af890b3b24501d7 — сервер выводит занятые слоты из живых lease, журналирует сверку и восстанавливает полную ёмкость после потери completion.

# CARD-0092 — Счётчик занятости воркера сам восстанавливается

## HEAD

- Status: Specification ready.
- Specification: `knowledge/specs/worker-active-capacity-self-recovery.md`.
- Scope: server-derived worker capacity, reconciliation audit и regression tests;
  UI, release и live configuration вне работы.
- Required evidence: `go test ./internal/controlplane ./internal/worker -run '^(TestClaimReconcilesStaleCachedCapacityWithoutWorkerRestart|TestReconnectAfterLostCompletionRestoresEveryWorkerSlot)$' -count=1` завершается кодом 0.

## Результат для владельца

После сбоя worker не оставляет призрачный занятый слот: следующая серверная
сверка возвращает доступную параллельность по живым lease, не дублируя текущую
работу. Retained worktree остаётся отдельным ограничителем репозитория.

## Scope реализации

- `migrations/026_worker_capacity_reconciliations.sql`
- `internal/protocol/types.go`
- `internal/controlplane/state.go`
- `internal/controlplane/store.go`
- `internal/controlplane/metrics.go`
- `internal/controlplane/store_test.go`
- `internal/controlplane/metrics_test.go`
- `internal/worker/registration.go`
- `internal/worker/reconcile.go`
- `internal/worker/worker_integration_test.go`

## Ограничения и следующее действие

Карточка определяет только текущую работу; не изменять UI, не удалять
`workers.active_count` и не смешивать capacity retained worktree с активной
попыткой. Следующее действие — реализация строго по спецификации с целевыми
регрессиями stale-count и lost-complete/reconnect.

## LOG

### 2026-08-11 — Specification

Зафиксированы источник истины, границы lease, транзакционные точки сверки,
метрики и проверяемые сценарии восстановления полной ёмкости без рестарта.
Номер `0092` свободен в свежем `origin/main` и опубликованных ветках; `0090` и
`0091` уже заняты другими работами.

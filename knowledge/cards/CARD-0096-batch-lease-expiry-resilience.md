# CARD-0096 — Активные работы не теряют lease синхронной пачкой

Implementation commit: 404fee2ce6a209ec78df32e295f5a8a9010b1866 — разнесены heartbeat-renewal, deadline-aware retry и короткая store-транзакция.

## HEAD

- Status: Implemented — готово к Verify.
- Branch: `factory/c7e2fc58-4b5-d166b0c2-474`.
- Specification: `knowledge/specs/batch-lease-expiry-resilience.md`.
- Owner impact: краткая очередь heartbeat-запросов больше не уничтожает разом
  активные агентские сессии одного worker.
- Scope: разнесённый deadline-aware renewal на worker и короткая транзакция
  heartbeat в control plane; без UI, миграции и изменения публичного API.
- Evidence: `go test -count=1 -run 'Test(ConcurrentAttemptsStaggerLeaseRenewalsUnderDelay|LeaseRenewalScheduleDispersesAttempts|HeartbeatDoesNotReconcileNeighboringExpiredLease)$' ./internal/worker ./internal/controlplane` → PASS; `git diff --check` → PASS.
- One next action: Verify прогонит полный `go test ./...` и проверит доставку ветки.

## LOG

### 2026-08-12 — Implement

На worker добавлен стабильный разброс renewal в диапазоне 70–100% интервала,
ограничение контекста оставшимся lease-бюджетом и обновление supervisor до записи
manifest. Heartbeat control plane теперь меняет только свою attempt; соседние
истёкшие попытки освобождаются штатным sweep. Целевые worker/control-plane тесты,
пачечный integration-сценарий и `git diff --check` прошли.

### 2026-08-12 — Specification

Фактический код показал общий failure mode: все attempt heartbeat-goroutine
используют одинаковые интервалы 10/2 секунды, а каждый renewal выполняет лишнюю
worker-wide capacity reconciliation внутри SQLite write-транзакции. Выбран
совместимый подход: распределить renewals по стабильной фазе, учитывать оставшийся
lease-бюджет и оставить heartbeat только продлением своей attempt. 30-секундный
fail-closed lease, endpoint и operator retry не меняются.

Предыдущая triage-ветка `factory/d3dc8ea2-3bb-cb2b6fde-b96` отсутствовала в
origin на момент Specification; выводы карточки опираются на свежий `origin/main`
и перечисленные регрессионные границы, а не на недоступный diff.

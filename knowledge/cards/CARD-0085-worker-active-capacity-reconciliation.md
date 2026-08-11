# CARD-0085 — Самовосстановление счётчика занятости воркера

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/b77bd6b3-1cc-c549126f-cd6`.
- Implementation commit: 7b0e963d2f8ae6c6d80570ed9af890b3b24501d7 — server-derived capacity,
  migration 026 и гарантированная очистка reconciliation journal.
- What changed: registration сохраняет старый `active_count` до server-time audit;
  registration и пустой `SweepExpired` однократно удаляют журнал старше восьми суток.
- What changed: integration покрывает потерянный `/complete`, restart/reconnect и
  две live barrier-задачи при `MaxConcurrent=2`; migration проверяет 025→026 и rollback-read.
- Evidence: `go test -timeout 20m ./... && go build ./...` → PASS (2:45.09);
  focused `go test -race -timeout 10m ... -count=1` → PASS (29.34s, 6 tests);
  fresh `origin/main...HEAD` → ровно 11 файлов, clean tree перед verify update.
- One next action: выполнить human merge в `main`.

## LOG

### 2026-08-11 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Полный build и test suite | `go test -timeout 20m ./... && go build ./...` | PASS, 2:45.09 |
| Migration 025→026 и rollback-read | focused race: `TestCapacityReconciliationMigrationUpgrades025AndKeepsRollbackReadable` | PASS |
| Idle retention и stale `active_count` при capacity=2 | focused race: sweep, claim и registration tests | PASS |
| Lost complete, restart/reconnect, все слоты и один live supervisor | focused race: `TestReconnectAfterLostCompletionRestoresEveryWorkerSlot` | PASS |
| Метрики reconciliation | focused race: `TestMetricsCountsCapacityReconciliationsInWindow` | PASS |
| Scope поставки | `git diff --name-only origin/main...HEAD` | PASS, ровно 11 файлов |

Focused-команда: `go test -race -timeout 10m ./internal/controlplane ./internal/worker
-run '^(TestMetricsCountsCapacityReconciliationsInWindow|TestSweepExpiredPrunesExpiredReconciliationRowsWhenWorkersAreIdle|TestClaimReconcilesStaleCachedCapacityWithoutWorkerRestart|TestRegistrationAuditsCachedCapacityBeforeReplacingIt|TestCapacityReconciliationMigrationUpgrades025AndKeepsRollbackReadable|TestReconnectAfterLostCompletionRestoresEveryWorkerSlot)$' -count=1` — PASS, 29.34s.

### 2026-08-11 — Specification

Зафиксирован воспроизводимый дефект: process-local `len(manager.slots)` попадает
в registration как `active_count`, а сохранённое значение затем участвует в
маршрутизации. Спецификация заменяет его авторитетным счётом незавершённых
непросроченных lease, определяет транзакционную сверку при registration,
claim/heartbeat и sweep, а также журнал расхождений. Номер `0085` проверен по
свежему `origin/main` и всем опубликованным `origin/*` веткам.

### 2026-08-11 — Implement

После strict review регистрация перестала затирать cached count до аудита: stale
`active_count` порождает ровно одну reconciliation-запись. Журнал ограничен тем
же восьмидневным server-time retention, что operational capacity samples; окно
метрик остаётся точным. Интеграция подтверждает потерю успешного `/complete`,
restart/reconnect control plane и заполнение обоих слотов без дублирования barrier supervisor.
Проверки: `go test ./internal/controlplane ./internal/worker`, `go test ./...`,
`git diff --check` — PASS; upgrade `025 -> 026` и rollback-read `active_count` покрыты тестом.

### 2026-08-11 — Implement

В чистой ветке от `origin/main` перенесён только набор CARD-0085. Очистка
reconciliation journal вынесена из условной коррекции в однократные server-time
maintenance paths регистрации и `SweepExpired`; idle regression подтверждает,
что старое окно удаляется без lease, а актуальная метрика остаётся точной.
Проверки: focused idle-retention, integration с `-timeout=90s`, `go test ./...`
и `git diff --check` — PASS.

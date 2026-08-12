# CARD-0085 — Самовосстановление счётчика занятости воркера

## HEAD

- Status: Implemented — ready for review.
- Branch: `factory/264b71ca-d92-3566e3c1-05e`.
- Implementation commit: e3bf54e08052819fbd2392fecec6e2399f7a0402 — worker передаёт фактически
  занятые локальные слоты старому control plane во время поэтапного обновления.
- What changed: новый server продолжает считать active capacity по lease, а старый
  control plane получает `len(manager.slots)` и не назначает второй supervisor.
- What changed: добавлены HTTP и integration регрессии для derived count, потери
  ответа, перезапуска worker и единственного supervisor.
- Evidence: `go test ./internal/controlplane ./internal/worker` → PASS;
  `go test ./... && go build ./...` → PASS; `git diff --check` → PASS.
- One next action: выполнить review и merge в `main`.

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

### 2026-08-12 — Implement

Для rolling upgrade worker снова передаёт число реально занятых local slots:
старый control plane не может выдать второй supervisor в работающий слот, а новый
остаётся authoritative по lease. HTTP и integration-проверки подтверждают derived
count, потерю ответа, restart и отсутствие duplicate supervisor. Проверено:
`go test ./internal/controlplane ./internal/worker`, `go test ./... && go build ./...`,
`git diff --check` — PASS.

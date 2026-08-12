# CARD-0085 — Самовосстановление счётчика занятости воркера

## HEAD

- Status: Implemented — candidate published for review.
- Branch: `factory/dc78470b-e09-ace20892-a0e`.
- Implementation commit: a86c425c8df764dc4672ab5fc7c5cf544c7253a1 — reconnect-тест
  подтверждает полное заполнение и последующее освобождение мощности воркера.
- What changed: после потери ответа `/complete` и restart control plane тест
  проверяет derived `active_count=2` для обеих barrier-задач.
- What changed: после их завершения тот же счётчик обязан стать `0`.
- Evidence: целевой `go test -race` → PASS; focused control-plane tests,
  `go build ./...` и `git diff --check` → PASS.
- One next action: выполнить review опубликованной кандидатской ветки.

## LOG

### 2026-08-12 — Implement

После reconnect worker и control plane регрессия теперь наблюдает authoritative
`active_count`: при двух live barrier-задачах он равен двум, после штатного
завершения — нулю. Это доказывает и полное восстановление мощности, и отсутствие
утечки занятости. Проверки: целевой `go test -race`, focused control-plane tests,
`go build ./...` и `git diff --check` — PASS.

### 2026-08-12 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Потерянный ответ, restart/reconnect и восстановление всех слотов | `go test -race -timeout 10m ./internal/controlplane ./internal/worker -run '^(TestMetricsCountsCapacityReconciliationsInWindow|TestSweepExpiredPrunesExpiredReconciliationRowsWhenWorkersAreIdle|TestClaimReconcilesStaleCachedCapacityWithoutWorkerRestart|TestRegistrationAuditsCachedCapacityBeforeReplacingIt|TestCapacityReconciliationMigrationUpgrades025AndKeepsRollbackReadable|TestReconnectAfterLostCompletionRestoresEveryWorkerSlot)$' -count=1` | PASS, controlplane 52.189s; worker 31.853s |
| Полный Go suite и сборка | `go test -timeout 20m ./...; go build ./...` | Go tests выявили существующий таймаут `TestSameRepositoryRuntimeAndCleanupCanOverlap`; сборка PASS |
| TypeScript-проверка веб-клиента | `cd web && npx tsc -p tsconfig.app.json --noEmit` | BLOCKED локально: TypeScript не установлен в окружении |
| Рабочее дерево и область поставки | `git status --short --branch` и pinned `base_sha...candidate_sha` comparison | чисто до записи этой карточки; кандидат меняет только эту карточку |

Целевые сценарии восстановления слотов проходят под `-race`. Полный suite имеет отдельный таймаут в worker integration test; TypeScript-проверка требует установки зависимости окружения.

### 2026-08-12 — Implement

Свежий `origin/main` уже содержит реализацию из commit `7b0e963d2f8ae6c6d80570ed9af890b3b24501d7`;
повторный перенос кода не потребовался. Целевая race-проверка шести сценариев,
`go build ./...` и `cd web && npx tsc -p tsconfig.app.json --noEmit` прошли.

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

# CARD-0085 — Самовосстановление счётчика занятости воркера

## HEAD

- Status: BLOCKED: полный Go-набор не проходит.
- Branch: `factory/a9af896c-8b9-442a68a7-a23`.
- Implementation commit: 277dfcd5e13ac7d6a3f20656517beaeb9c710a8a — серверная сверка
  active capacity по действующим lease и журнал коррекций.
- What changed: cached `active_count` теперь только совместимый снимок; claim,
  registration, heartbeat, terminal transition и sweep сверяют его по server time.
- What changed: добавлены migration 026 и оконные метрики reconciliation/ghost slots;
  retained worktrees не участвуют в derived worker capacity.
- Evidence: целевой stale-count сценарий и метрика → PASS; `go test ./...` → FAIL
  (тайм-аут `internal/worker` через 10 минут); `git diff --check` → PASS.
- One next action: устранить блокировку heartbeat/SQLite в интеграционных worker-тестах и повторить полный Go-набор.

## LOG

### 2026-08-11 — Specification

Зафиксирован воспроизводимый дефект: process-local `len(manager.slots)` попадает
в registration как `active_count`, а сохранённое значение затем участвует в
маршрутизации. Спецификация заменяет его авторитетным счётом незавершённых
непросроченных lease, определяет транзакционную сверку при registration,
claim/heartbeat и sweep, а также журнал расхождений. Номер `0085` проверен по
свежему `origin/main` и всем опубликованным `origin/*` веткам.

### 2026-08-11 — Implement

Реализована транзакционная сверка занятости: только непросроченные server-time
lease в `preparing`/`running` занимают slot; просроченные попытки условно
становятся `lost` и освобождаются exactly once. Migration 026 добавляет
append-only журнал коррекций, а metrics отдают reconciliation и ghost slots.
Регрессия seeded stale `active_count=1` при capacity=2 получает две lease без
рестарта. Проверки: `go test ./internal/controlplane ./internal/worker`,
`go test ./...`, `git diff --check` — PASS.

### 2026-08-12 — Verify

| Критерий | Команда / проверка | Наблюдение |
| --- | --- | --- |
| Устаревший cached count не блокирует capacity=2 | `go test ./internal/controlplane -run 'TestClaimReconcilesStaleCachedCapacityWithoutWorkerRestart|TestMetricsCountsCapacityReconciliationsInWindow' -count=1` | PASS за 4.505s: выданы две lease, derived count равен 2, журнал сверки создан. |
| Изменение не содержит ошибок формата | `git diff --check fc3af293e5e2b2c3802ad9b1d376f7796aa3b067...af51039f4cc6e9a085b96c38e4f82dad853cd3b4` | PASS. |
| Полный регрессионный набор | `go clean -testcache && go test ./...` в чистом клоне | FAIL: `internal/worker` timeout 600.329s; завис `TestFailureRetainsWorktree`, до него не уложились семь worker-интеграций. Stack показывает heartbeat, ожидающий SQLite transaction. |

Итог: merge блокирован до устранения worker-регрессии. Тестовый клон и
закреплённое сравнение не содержат посторонних изменений.

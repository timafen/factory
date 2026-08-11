# CARD-0085 — Самовосстановление счётчика занятости воркера

## HEAD

- Status: Implemented — ready for review.
- Branch: `factory/a9af896c-8b9-442a68a7-a23`.
- Implementation commit: 277dfcd5e13ac7d6a3f20656517beaeb9c710a8a — серверная сверка
  active capacity по действующим lease и журнал коррекций.
- What changed: cached `active_count` теперь только совместимый снимок; claim,
  registration, heartbeat, terminal transition и sweep сверяют его по server time.
- What changed: добавлены migration 026 и оконные метрики reconciliation/ghost slots;
  retained worktrees не участвуют в derived worker capacity.
- Evidence: `go test ./internal/controlplane ./internal/worker` → PASS;
  `go test ./...` → PASS; `git diff --check` → PASS.
- One next action: проверить изменение в review и выполнить merge после обычной проверки.

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

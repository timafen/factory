# CARD-0085 — Самовосстановление счётчика занятости воркера

## HEAD

- Status: Specification — ready for Implement.
- Branch: `factory/f17b716b-9fa-05d63446-fd4`.
- Scope: authoritative capacity is reconstructed from leased attempts; retained
  worktrees remain repository-retention state and never become worker slots.
- One next action: реализовать `knowledge/specs/worker-active-capacity-reconciliation.md`.

## LOG

### 2026-08-11 — Specification

Зафиксирован воспроизводимый дефект: process-local `len(manager.slots)` попадает
в registration как `active_count`, а сохранённое значение затем участвует в
маршрутизации. Спецификация заменяет его авторитетным счётом незавершённых
непросроченных lease, определяет транзакционную сверку при registration,
claim/heartbeat и sweep, а также журнал расхождений. Номер `0085` проверен по
свежему `origin/main` и всем опубликованным `origin/*` веткам.

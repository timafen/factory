# CARD-0085 — Самовосстановление счётчика занятости воркера

## HEAD

- Status: Implemented — ready for review.
- Branch: `factory/b77bd6b3-1cc-c549126f-cd6`.
- Implementation commit: 7b0e963d2f8ae6c6d80570ed9af890b3b24501d7 — server-derived capacity,
  migration 026 и гарантированная очистка reconciliation journal.
- What changed: registration сохраняет старый `active_count` до server-time audit;
  registration и пустой `SweepExpired` однократно удаляют журнал старше восьми суток.
- What changed: integration покрывает потерянный `/complete`, restart/reconnect и
  две live barrier-задачи при `MaxConcurrent=2`; migration проверяет 025→026 и rollback-read.
- Evidence: focused idle-retention, `go test ./internal/controlplane ./internal/worker`,
  `go test ./...`, `git diff --check` → PASS.
- One next action: проверить clean three-dot diff перед merge.

## LOG

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

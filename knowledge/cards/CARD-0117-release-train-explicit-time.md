# CARD-0117 — Поезд выпуска не зависит от часов машины

Implementation commit: 517f1a4780cdbf34cc2e22753b7a844d6068b2e0 — проекция поезда принимает только явное время снимка

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/2fc80eda-1e1-d7e153ad-ca8`.
- Implementation commit: `517f1a4780cdbf34cc2e22753b7a844d6068b2e0`.
- What changed: `release_train_block` требует переданный момент снимка; системные часы больше не являются запасным источником для `updated_at` и длительности.
- Evidence: pinned `main` `1ff5d59db1c5dd0cb33a3db26255ee43c88e3517` → candidate `b2cef2f777bdbec1cc76ee9ed493d2a17976bf22`; target tests PASS (6), Go suite PASS; full Python suite has 2 unrelated restart/provenance failures.
- Next action: влить ветку в `main`.

## LOG

### 2026-08-13 — Implement

Убран неявный fallback на часы машины из проекции «Поезд выпуска». Новый
regression-тест фиксирует время снимка и durable `started_at`, запрещая вызов
`pilot.time.time`; `updated_at` и `elapsed_seconds` остаются детерминированными.

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Проекция не читает часы машины | `python3 -m unittest pilot.test_pilot.ReleaseTrainDashboardTests` | PASS, 6 тестов; вызов `pilot.time.time` запрещён mock-проверкой |
| Временные поля считаются от снимка и durable timestamp | тот же целевой набор | PASS: `updated_at` и `elapsed_seconds` совпали с фиксированным `now` |
| Регрессии соседнего кода | `go test -timeout 5m ./...` | PASS; полный Python-набор — 249 PASS, 2 существующих сбоя в restart/provenance |

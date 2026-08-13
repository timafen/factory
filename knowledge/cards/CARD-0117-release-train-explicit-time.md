# CARD-0117 — Поезд выпуска не зависит от часов машины

Implementation commit: 517f1a4780cdbf34cc2e22753b7a844d6068b2e0 — проекция поезда принимает только явное время снимка

## HEAD

- Status: Implemented and verified.
- Branch: `factory/5a1f7437-8a6-0e2cd055-656`.
- Implementation commit: `517f1a4780cdbf34cc2e22753b7a844d6068b2e0`.
- What changed: `release_train_block` требует переданный момент снимка; системные часы больше не являются запасным источником для `updated_at` и длительности.
- Evidence: `python3 -m unittest pilot.test_pilot.ReleaseTrainDashboardTests` → PASS (6 tests), включая запрет `pilot.time.time` в regression-тесте.
- Next action: влить ветку в `main`.

## LOG

### 2026-08-13 — Implement

Убран неявный fallback на часы машины из проекции «Поезд выпуска». Новый
regression-тест фиксирует время снимка и durable `started_at`, запрещая вызов
`pilot.time.time`; `updated_at` и `elapsed_seconds` остаются детерминированными.

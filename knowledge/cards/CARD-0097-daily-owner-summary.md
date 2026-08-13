# CARD-0097 — Ежедневная сводка владельцу о влитом и выпущенном

Implementation commit: 601c63f303049be76763dc27866941e2d4f818f2 — Pilot формирует и идемпотентно доставляет ежедневную сводку из подтверждённых receipt и метрик.

## HEAD

- Status: Implement + Test complete; ready for Review.
- Branch: `factory/aa572338-947-93ed87dd-1f3`.
- Schedule: `0 8 * * *`, timezone `America/Chicago`, один logical event на местную дату.
- Delivery: durable snapshot до ntfy push, стабильный ntfy sequence и минутный retry после ошибки.
- Sources: merge receipt, accepted live delivery receipt, dashboard health metrics и terminal blocked tasks.
- Evidence: `python3 -m unittest pilot.test_pilot.DailyOwnerSummaryTests` → 4 tests OK.
- Evidence: целевые Pilot tests → 19 tests OK; control-plane schedule tests → PASS; `just build` → 3 binaries.
- Next action: Review должен проверить pinned diff реализации относительно свежего default branch.

## LOG

### 2026-08-12 — Specification

- Specification: `knowledge/specs/daily-owner-summary.md`.
- Owner decision: ежедневно в 08:00, timezone `America/Chicago`, максимум одна сводка на местную календарную дату.
- Channel: `https://ntfy.sh/timafen-a8523d037f21`.
- Scope: durable Pilot snapshot, scheduler occurrence, deduplicated outbox delivery и целевые тесты; UI не требуется.

Фактический код уже хранит merge/delivery receipts, durable outbox,
`recent_done_block`, метрики и IANA-aware scheduler. Спецификация добавляет
ежедневный snapshot и дату-ключ дедупликации, чтобы владелец видел только
подтверждённое влитие/выпуск и измеримый результат без дублей после restart.

Предыдущая triage-ветка `factory/9fc5ce2e-b9b-78c47023-b17` отсутствует в
origin; это зафиксировано как инфраструктурное ограничение, а не причина
менять чужую карточку.

### 2026-08-12 — Implement

Pilot резервирует immutable snapshot до внешней отправки, повторяет pending
event с тем же ntfy sequence и после успеха больше его не отправляет. Сводка
различает merge, accepted live release, изменение/нулевой эффект/неизвестность
метрик и terminal blockage. Доказательство: 4 обязательных теста сводки и 15
соседних Pilot-тестов прошли; cron/DST Go-тесты и сборка трёх бинарников прошли.

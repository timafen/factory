# CARD-0097 — Ежедневная сводка владельцу о влитом и выпущенном

Implementation commit: будет добавлен на этапе Implement — Specification не изменяет исходники приложения.

- Status: Specification complete; implementation not started.
- Specification: `knowledge/specs/daily-owner-summary.md`.
- Owner decision: ежедневно в 08:00, timezone `America/Chicago`, максимум одна сводка на местную календарную дату.
- Channel: `https://ntfy.sh/timafen-a8523d037f21`.
- Scope: durable Pilot snapshot, scheduler occurrence, deduplicated outbox delivery и целевые тесты; UI не требуется.
- Next action: Implement должен добавить реализацию и заменить эту строку полным SHA implementation-коммита.

## Specification log — 2026-08-12

Фактический код уже хранит merge/delivery receipts, durable outbox,
`recent_done_block`, метрики и IANA-aware scheduler. Спецификация добавляет
ежедневный snapshot и дату-ключ дедупликации, чтобы владелец видел только
подтверждённое влитие/выпуск и измеримый результат без дублей после restart.

Предыдущая triage-ветка `factory/9fc5ce2e-b9b-78c47023-b17` отсутствует в
origin; это зафиксировано как инфраструктурное ограничение, а не причина
менять чужую карточку.

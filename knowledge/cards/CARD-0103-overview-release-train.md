# CARD-0103 — Обзор показывает поезд выпуска

Implementation commit: 10ed51b9b3331daaf0660fcd9e84c2cc5449324d — подготовлена проверяемая спецификация проекции состояния выпуска на Обзор.

## HEAD

- Status: Specified — ожидает реализации.
- Specification: `knowledge/specs/overview-release-train.md`.
- Owner impact: на «Обзоре» появится честный ответ, что едет в текущем выпуске, на каком он шаге и есть ли следующий состав.
- Scope: только dashboard projection и Overview; broker, очередь, release adapter и хранилище не меняются.
- Required check: `python3 -m unittest pilot.test_pilot.ReleaseTrainDashboardTests`.

## LOG

### 2026-08-12 — Specification

Зафиксирован единый read-only снимок `release_train` из существующего
`delivery_state_v2`, публикуемый вместе с остальным `dashboard.json`.
`reserved` трактуется как текущий состав, а `next_requested` — только как
следующий после терминального текущего; дата разрешена лишь из известного
`next_retry_at`. Спецификация требует UI- и API-контрактные тесты для
свободного, ожидающего, выполняющегося, успешного и ошибочного выпуска.

Номер и путь карточки проверены свободными в свежем `origin/main` и всех
опубликованных ветках; более ранние номера 0097–0102 уже используются
параллельными работами.

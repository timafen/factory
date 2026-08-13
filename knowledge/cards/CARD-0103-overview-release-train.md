# CARD-0103 — Обзор показывает поезд выпуска

Implementation commit: a25b0ddceb4d687361ae2847ef569d4851825b8e — Обзор показывает текущий и следующий поезд из durable-состояния выпуска.

## HEAD

- Status: Implemented — ожидает Review.
- Branch: `factory/2ba63f51-491-8010ae39-9a7`.
- Specification: `knowledge/specs/overview-release-train.md`.
- What changed: `dashboard.json` получил безопасную проекцию поезда; Overview показывает его состояние, пассажиров, известное время и следующий состав.
- Scope: только dashboard projection и Overview; broker, очередь, release adapter и хранилище не меняются.
- Evidence: 5 projection tests, 10 delivery regressions и 28 Overview tests — PASS; `just check` и `just build` — PASS.
- Open finding: полный Python-набор — 245 PASS, 2 FAIL в несвязанном `CorrectionProvenanceStormTests` (устойчиво отдельно).
- Next action: провести Review implementation-коммита и проверить формулировки блока на Overview.

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

### 2026-08-12 — Implement

Добавлена read-only проекция `release_train` из `delivery_state_v2` и блок
«Поезд выпуска» между общим статусом и текущими работами. В публичный JSON
не попадают SHA, PID и внутренний generation id; неизвестное время не
выдумывается. Целевые Python/UI-тесты, регрессии доставки, `just check` и
сборка прошли. Полный Python-набор выявил два устойчивых сбоя вне области —
в тесте перезапуска коррекций Review/Verify.

# CARD-0084 — Единая машина состояний слияния и выпуска

## HEAD

- Status: Specified — ожидает реализации и проверки.
- Branch: `factory/3b5d6236-fb9-13925b8c-917`.
- Specification: `knowledge/specs/merge-release-delivery-state-machine.md`.
- Implementation commit: —.
- What changed: определён единый durable lifecycle для merge, выпуска,
  delivery wait и уведомления; финальное «Задача выполнена» возможно только
  после принятого выпуска конкретного поколения.
- Evidence: прочитаны `pilot/pilot.py`, `pilot/test_pilot.py`,
  `internal/releasebroker/`, `cmd/factory-release-broker/` и
  `ops/fx-factory-release`; CARD-0083 обнаружена в опубликованных ветках, а
  CARD-0084 и этот путь свободны на `origin/main` и всех опубликованных refs.
- Next action: Implement выполняет изолированный diff из спецификации и
  начинает с тестов полного restart-cycle.

## LOG

### 2026-08-11 — Specification

Текущее состояние `post_merge_deploys` смешивает поколение, reservation,
PID, результат и запрос следующего выпуска в полях `queued`, `pid` и
`status`; `cycle()` пишет merge-journal и вызывает `notify("Задача
выполнена")` сразу после `gh_merge`. Поэтому владелец может увидеть готовую
работу до живой приёмки, а restart нельзя однозначно восстановить.

В review-истории CARD-0077 зафиксированы прежние crash-окна после `gh_merge`,
до journal и между Popen/PID; эти находки использованы только как evidence, их
ветки не объединялись. Выбрана новая минимальная архитектура: immutable
generation id, пять явных фаз, merge-intent до внешнего merge,
generation-specific idempotent broker/status и delivery wait, привязанный к
поколению. Старые флаги не сохраняются как совместимая рабочая модель.

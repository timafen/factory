# CARD-0136 — Доиграть передачу этапа после рестарта Pilot

Implementation commit: 147bb0e31a4243c15be38e19b926a61c505118c2 — recovery читает реальные временные поля detail, а watermark удерживается до успешной или отложенной обработки.

## HEAD

- Status: Implemented + tested — ожидает Review.
- Branch: `factory/eb975ba5-c9a-f4ba8c5b-e65`.
- What changed: startup recovery получает timestamp из detail (`execution.updated_at`
  или `attempts[].completed_at`), а временный сбой, лимит или backlog удерживают
  watermark для следующей попытки.
- Safety: lifecycle/stop, известный нефинальный workflow и `live_or_done_at()`
  закрывают старые работы и дубли; fixture больше не подмешивает поля списка задач.
- Evidence: `python3 -m unittest pilot.test_pilot.AdaptivePollingTests` — 18 OK;
  `git diff --check` — OK.
- Source contract: CARD-0155 и specification head
  `7e8eb284d89160704292add3b7609cae272b1c8c`.
- Next action: Review проверяет границы startup-recovery и финальный duplicate guard.

## LOG

### 2026-08-14 — Implement

Добавлены durable watermark и неизменяемый startup-набор уже обработанных ID.
Свежий successful terminal-этап без фактического хвоста проходит обычные
`decide`, worker/capacity/area guards и `create_child_task`; временный отказ
повторяется, а live/succeeded хвост, stop, закрытие, старая или неполная
terminal-метка, неизвестный и финальный этап безопасно подавляют восстановление.
Целевая команда и новые табличные проверки завершились `OK`, сборка прошла.

### 2026-08-14 — Implement

Исправлено чтение времени завершения: список `/tasks` больше не используется как
источник несуществующих `finished_at`/`updated_at`, recovery читает detail API.
Watermark не продвигается при временном отказе handoff, дневном лимите,
terminal backlog или невидимом startup-кандидате. Целевой класс: 18 тестов OK.

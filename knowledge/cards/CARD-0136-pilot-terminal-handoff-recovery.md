# CARD-0136 — Доиграть передачу этапа после рестарта Pilot

Implementation commit: 3ee43a7631eea64ccab32b7bf922ecc6f6273528 — Pilot восстанавливает пропущенный handoff только для свежего безопасного завершения и не создаёт существующий хвост повторно.

## HEAD

- Status: Implemented + tested — ожидает Review.
- Branch: `factory/25e696e9-050-bcbdda75-9b4`.
- What changed: startup-снимок `processed` и watermark последнего успешного
  цикла разрешают повторить потерянный handoff через штатный обработчик.
- Safety: lifecycle/stop, terminal timestamp, известный нефинальный workflow и
  две проверки `live_or_done_at()` закрывают старые работы и дубли.
- Evidence: целевая restart-регрессия — `OK`; 4 recovery-сценария — `OK`;
  соседние restart/cursor тесты — `OK`; `just build` — успешно.
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

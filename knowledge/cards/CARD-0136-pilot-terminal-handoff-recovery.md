# CARD-0136 — Доиграть передачу этапа после рестарта Pilot

Implementation commit: ca6c904c43e128f402cef8a9c50cc2f2e449383a — все временные retry-пути удерживают recovery watermark, включая блокировку области и отсутствие workflow/worker.

## HEAD

- Status: Implemented + tested — повторно ожидает Review.
- Branch: `factory/505ed710-017-e98b74ed-710`.
- What changed: единый retry-helper удаляет terminal ID из `processed` и удерживает
  startup watermark во всех временных ветках, включая `area_busy` и отсутствие
  workflow/worker; handoff переживает сохранение state и второй рестарт.
- Safety: lifecycle/stop, известный нефинальный workflow и `live_or_done_at()`
  закрывают старые работы и дубли; fixture больше не подмешивает поля списка задач.
- Evidence: `python3 -m unittest pilot.test_pilot.AdaptivePollingTests` — 19 OK;
  `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` и `git diff --check` — OK.
- Source contract: CARD-0155 и specification head
  `7e8eb284d89160704292add3b7609cae272b1c8c`.
- Next action: повторный Review проверяет централизованный retry-инвариант.

## LOG

### 2026-08-14 — Implement

После замечания Review все ветки, повторно ставящие terminal-задачу через удаление
из `processed`, переведены на единый helper, который удерживает startup watermark.
Регрессия воспроизводит `area_busy`, сохраняет и загружает state как новый процесс,
после чего подтверждает создание handoff; целевой класс: 19 тестов OK.

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

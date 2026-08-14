# CARD-0136 — Доиграть передачу этапа после рестарта Pilot

Implementation commit: ca6c904c43e128f402cef8a9c50cc2f2e449383a — все временные retry-пути удерживают recovery watermark, включая блокировку области и отсутствие workflow/worker.

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/505ed710-017-e98b74ed-710`.
- What changed: единый retry-helper удаляет terminal ID из `processed` и удерживает
  startup watermark во всех временных ветках, включая `area_busy` и отсутствие
  workflow/worker; handoff переживает сохранение state и второй рестарт.
- Safety: lifecycle/stop, известный нефинальный workflow и `live_or_done_at()`
  закрывают старые работы и дубли; fixture больше не подмешивает поля списка задач.
- Evidence: `python3 -m unittest pilot.test_pilot.AdaptivePollingTests` — 19 OK;
  полный `python3 -m unittest pilot.test_pilot` — 274 выполнено, 2 известных
  падения `CorrectionProvenanceStormTests`, воспроизводятся на закреплённой базе;
  `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` и `git diff --check` — OK.
- Source contract: CARD-0155 и specification head
  `7e8eb284d89160704292add3b7609cae272b1c8c`.
- Next action: human merge проверяет известные базовые падения отдельно от CARD-0136.

## LOG

### 2026-08-14 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Незавершённый handoff переживает рестарт и повторную попытку | `python3 -m unittest pilot.test_pilot.AdaptivePollingTests` | 19 OK, включая temporary create failure и второй рестарт после `area_busy` |
| Повторное восстановление не создаёт continuation при существующем хвосте | тот же целевой класс: `test_restart_recovery_rejects_unsafe_or_completed_candidates` | OK |
| Recovery watermark продвигается только после успешного handoff | тот же целевой класс: `test_loop_moves_recovery_watermark_only_after_success`, `test_loop_keeps_recovery_watermark_when_handoff_is_pending` | OK |
| Смежные lifecycle/cursor и polling-пути не регрессировали | полный `python3 -m unittest pilot.test_pilot` | 274 выполнено; 2 failures воспроизводятся на base, новых failures нет; кандидат также устраняет 2 base errors `StopIteration` |

Проверены также `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` и
`git diff --check`: оба успешно. Известные failures относятся к
`CorrectionProvenanceStormTests` и присутствуют в закреплённой базе; они не
являются регрессией CARD-0136.

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

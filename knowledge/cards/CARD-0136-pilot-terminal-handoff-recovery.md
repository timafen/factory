# CARD-0136 — Доиграть передачу этапа после рестарта Pilot

Implementation commit: 65d1cb13aef89faafd85f507e6f70b60c28fa16d — Pilot доигрывает пропущенный handoff после рестарта и не глотает чужие завершения.

## HEAD

- Status: Implemented — ready for Verify.
- Branch: `factory/e498bb54-b4c-0b53b929-494`.
- Implementation commit: `65d1cb13aef89faafd85f507e6f70b60c28fa16d` — durable startup watermark и безопасное восстановление handoff.
- What changed: после рестарта Pilot повторяет только terminal-кандидатов, завершённых
  после watermark и без живого/готового хвоста; временные retry-пути watermark не продвигают.
- Evidence: `python3 -m unittest pilot.test_pilot.AdaptivePollingTests` — 19 OK;
  `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` и `git diff --check` — OK.
- One next action: Verify должен один раз прогнать полный набор на этой кандидатной ветке.

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

### 2026-08-14 — Implement

После переноса на свежую `main` durable startup watermark и immutable startup-набор
сохранены во всех retry-ветках, включая `area_busy` и второй рестарт процесса.
Проверено: `python3 -m unittest pilot.test_pilot.AdaptivePollingTests` — 19 OK;
`py_compile` и `git diff --check` — OK. Implementation commit: `65d1cb13aef89faafd85f507e6f70b60c28fa16d`.

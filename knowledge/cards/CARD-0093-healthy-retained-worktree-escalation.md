Implementation commit: 394a367ebb1d1ca77f7b811cd95657de94e342d1 — healthy retained эскалируется идемпотентно в утверждённый канал владельца по умолчанию без очистки результата.

# CARD-0093 — Эскалация retained worktree здорового исполнителя

## HEAD

- Status: Implemented — checks and live delivery pass
- Branch: `factory/4d7cf287-b29-286b7e0c-27d`
- Implementation commit: `394a367ebb1d1ca77f7b811cd95657de94e342d1`
- Specification: `knowledge/specs/healthy-retained-worktree-escalation.md`
- What changed: healthy online retained получает одну durable-эскалацию на
  точный снимок через `https://ntfy.sh/timafen-a8523d037f21` по умолчанию;
  сбой канала не помечает событие доставленным и оставляет его для повтора.
- Evidence: `bash ops/test-factory-janitor.sh` — 7 сценариев PASS; два живых
  запуска — одна доставка/один snapshot; `just test` и `just build` — PASS.
- Next action: проверить этапом Verify и влить ветку в `main`.

## LOG

### 2026-08-12 — Specification

Зафиксирован разрыв после разделения offline/unhealthy очистки: healthy online с
retained worktree больше не останавливается, но также не попадает ни в очистку,
ни в эскалацию. Следующий этап должен добавить отдельный durable поток
уведомления, не ослабляя защиту результата и не меняя API очистки.

### 2026-08-12 — Implement

В `ops/factory-janitor.sh` добавлен отдельный notification-only поток для
online healthy retained worktree с durable ключом точного снимка. Целевой тест
подтвердил однократную доставку, повтор для изменённой причины, безопасный сбой
канала и неизменность существующей offline/unhealthy очистки: 6 сценариев PASS.

### 2026-08-12 — Implement

Утверждённый ntfy-канал задан production-default и покрыт сценарием без
переменной окружения. Целевой тест дал 7 PASS; два живых запуска отправили одно
уведомление и сохранили один snapshot; `just test` и `just build` прошли.

## Проверка готовности

| Критерий | Проверка |
| --- | --- |
| Healthy retained не трогается | `bash ops/test-factory-janitor.sh` фиксирует отсутствие stop/mv/POST |
| Эскалация однократна и переживает рестарт | тот же тест с повторным запуском и state |
| Изменённый снимок замечается | тот же тест с новым path/reason |
| Старые cleanup-сценарии сохранены | тот же целевой shell-тест |

ГОТОВО-КОГДА: файл ops/factory-janitor.sh
ГОТОВО-КОГДА: файл ops/test-factory-janitor.sh
ГОТОВО-КОГДА: команда bash ops/test-factory-janitor.sh

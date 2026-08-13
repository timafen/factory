Implementation commit: c850eebe5528a7c33c34b661c00df47cf567ed0c — healthy retained эскалируется идемпотентно, а unhealthy retained очищается через карантин.

# CARD-0093 — Эскалация retained worktree здорового исполнителя

## HEAD

- Status: Implemented — targeted checks pass
- Branch: `factory/113d4a38-8aa-4624be9d-a9f`
- Implementation commit: `c850eebe5528a7c33c34b661c00df47cf567ed0c`
- Specification: `knowledge/specs/healthy-retained-worktree-escalation.md`
- What changed: healthy online retained получает одну durable-эскалацию на
  точный снимок; online unhealthy retained теперь переносится в карантин и
  подтверждается существующим API очистки, как и offline retained.
- Evidence: `bash ops/test-factory-janitor.sh` — 8 сценариев PASS, включая
  очистку retained worktree у online unhealthy исполнителя.
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

### 2026-08-12 — Implement

Online unhealthy исполнитель с retained worktree включён в существующий поток
карантина и API-подтверждения очистки. Целевой тест сохранил прежний сценарий
unhealthy без retained и добавил восьмой сценарий очистки unhealthy retained:
`bash ops/test-factory-janitor.sh` — 8 PASS.

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

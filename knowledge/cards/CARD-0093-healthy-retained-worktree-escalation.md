Implementation commit: 33aa4b58d7f949420ba4d86cfc9639038fa0f3c8 — базовая реализация санитарного отбора retained worktree до этапа эскалации.

# CARD-0093 — Эскалация retained worktree здорового исполнителя

## HEAD

- Status: Specification — awaiting implementation
- Branch: `factory/acbce571-a16-a944abc7-d44`
- Specification: `knowledge/specs/healthy-retained-worktree-escalation.md`
- Scope: healthy online retained остаётся нетронутым, но получает одну
  идемпотентную эскалацию владельцу.
- Implementation files: `ops/factory-janitor.sh`, `ops/test-factory-janitor.sh`

## LOG

### 2026-08-12 — Specification

Зафиксирован разрыв после разделения offline/unhealthy очистки: healthy online с
retained worktree больше не останавливается, но также не попадает ни в очистку,
ни в эскалацию. Следующий этап должен добавить отдельный durable поток
уведомления, не ослабляя защиту результата и не меняя API очистки.

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

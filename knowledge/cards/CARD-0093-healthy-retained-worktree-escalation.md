Implementation commit: 8022bff9482a2215447a86876f85276c2267dbf6 — добавлена идемпотентная эскалация retained worktree здорового исполнителя без очистки результата.

# CARD-0093 — Эскалация retained worktree здорового исполнителя

## HEAD

- Status: Implemented — target tests pass
- Branch: `factory/722112d6-de2-d418d077-8a0`
- Implementation commit: `8022bff9482a2215447a86876f85276c2267dbf6`
- Specification: `knowledge/specs/healthy-retained-worktree-escalation.md`
- What changed: healthy online retained получает одну durable-эскалацию на
  точный снимок; сбой канала оставляет результат на месте и доступен для повтора.
- Evidence: `bash ops/test-factory-janitor.sh` — 6 сценариев PASS; Go, UI,
  tooling и launcher checks — PASS; `just build` — PASS.
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

Implementation commit: c850eebe5528a7c33c34b661c00df47cf567ed0c — на предыдущей ветке этой работы подтверждён реализуемый поток эскалации; текущая поставка фиксирует только спецификацию.

# CARD-0172 — Эскалация retained worktree здорового исполнителя

## HEAD

- Status: Specification ready
- Branch: `factory/2a401df9-ccd-c3b1a7cf-3d9`
- Specification: `knowledge/specs/healthy-retained-worktree-escalation.md`
- Owner outcome: здоровый исполнитель сохраняет удержанный результат, а
  владелец один раз получает понятное уведомление и может решить судьбу
  worktree вручную.
- Scope: `ops/factory-janitor.sh`, `ops/test-factory-janitor.sh`.
- Required check: `bash ops/test-factory-janitor.sh`.
- Next action: реализовать спецификацию на свежем `main`, не перенося код в
  текущий документационный этап.

## LOG

### 2026-08-15 — Specification

На свежем `origin/main` подтверждён разрыв: janitor очищает только offline
retained, а online healthy retained тестируется лишь на сохранность. Определён
отдельный notification-only путь с durable дедупликацией точного snapshot,
повтором после ошибки доставки, локальным fallback и ограниченным state.

Предыдущая ветка работы использована как источник triage-фактов и прототипа;
продуктовые изменения из неё в эту specification-ветку не переносились.

## Проверка готовности

| Критерий | Проверка |
| --- | --- |
| Healthy retained не очищается | целевой тест не фиксирует stop, mv, prune или cleanup POST |
| Новый snapshot эскалируется один раз | два запуска с общим state дают одно уведомление |
| Изменение snapshot замечается | новый attempt/repository/path/reason даёт второе уведомление |
| Сбой канала безопасен и retryable | worktree сохранён, ошибка записана, следующий запуск доставляет |
| Старый cleanup не регрессирует | offline retained по-прежнему проходит карантин и точный clear POST |

ГОТОВО-КОГДА: файл ops/factory-janitor.sh
ГОТОВО-КОГДА: файл ops/test-factory-janitor.sh
ГОТОВО-КОГДА: команда bash ops/test-factory-janitor.sh

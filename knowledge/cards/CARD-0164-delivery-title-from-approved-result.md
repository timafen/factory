# CARD-0164 — Поставка называется подтверждённым результатом

Implementation commit: отсутствует — этап Specification определяет реализацию, но не подменяет её документационным SHA.

## HEAD

- Status: Planned
- Branch: `factory/675e7b9e-48e-851cfa5e-67a`
- What changes: PR, выпуск и уведомление получают отдельный проверенный
  `delivery_title` из subject подтверждённого implementation commit либо из
  явного override текущего Verify; исходный problem title остаётся только
  идентификатором работы.
- Evidence: спецификация сверена с текущими `gh_merge`,
  `recover_merge_intents`, `resume_merge_conflicts`, delivery outbox и
  проверкой `Implementation commit` в `pilot/pilot.py`.
- Next action: Implement + Test реализует контракт в `pilot/pilot.py` и
  `pilot/test_pilot.py`, затем запишет настоящий предшествующий code commit.

## LOG

### 2026-08-15 — Specification

Определены происхождение и приоритет title, предел 72 символа, запрещённые
служебные формы, безопасный возврат в Verify и сохранение через рестарт и
merge conflict. `base` и `work_id` не меняются; squash merge, release scripts
и исторические PR вне области. Полный план, критерии и тест-план находятся в
`knowledge/specs/delivery-title-from-approved-result.md`.

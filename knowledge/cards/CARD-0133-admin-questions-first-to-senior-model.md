Implementation commit: b7ac7e202a7427ea82a6fe16404650faffc75a3d — обычные циклы ограничены, а ошибка fx передаётся старшей модели без повторного admin_action.

# CARD-0133 — Административные вопросы сначала решает старшая модель

## HEAD

- Статус: Implemented; целевые проверки PASS, ожидает Review/Verify.
- Ветка: `factory/f8a9cba3-553-0d3e07d9-468`.
- Implementation commit: `b7ac7e202a7427ea82a6fe16404650faffc75a3d` — ограничены обычные loop-rescue и обработан ошибочный результат `fx` без повторного admin_action.
- Что изменено: после исчерпания `max_loop_rescues` обычный ответ не продлевает цикл, но разрешённое admin-действие сохраняет отдельный путь; ошибка `fx` передаётся старшей модели и остаётся эскалацией владельцу.
- Evidence: `python3 -m unittest pilot.test_pilot.OrchestratorWaitActionTests pilot.test_pilot.AdminQuestionRoutingTests pilot.test_pilot.DiagnosisRepairTests` → PASS: 32/32; `go test ./internal/controlplane` → PASS.
- Следующее действие: повторно провести Review/Verify и проверить push этой ветки.

## LOG

### 2026-08-13 — Implement

Готовая поставка CARD-0116 штатно перенесена одним squash-коммитом на свежий
`origin/main`. Старшая модель выполняет только allowlist-проверки staging, затем
получает результат для решения; владелец видит только явные эскалации. Целевые
Go- и Python-тесты прошли, проверка пробелов diff также успешна.

### 2026-08-13 — Implement

После замечаний Review восстановлено ограничение обычных loop-rescue: ответы
старшей модели больше не продлевают цикл после `max_loop_rescues`, но отдельный
разрешённый `admin_action` по-прежнему проходит через `fx`. Ошибка `fx` теперь
передаётся старшей модели с запретом нового `admin_action`, сохраняется в аудите
и эскалируется владельцу. Проверено 32 целевыми Python-тестами и
`go test ./internal/controlplane`; код-коммит — `b7ac7e202a7427ea82a6fe16404650faffc75a3d`.
Дубликат CARD-0116 удалён, а спецификация теперь ссылается на эту карточку.

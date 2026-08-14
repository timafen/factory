# CARD-0127: административные вопросы через старшую модель

Implementation commit: pending — реализация будет выполнена на следующем этапе после Specification

Status: Specification — ожидает Implement
Branch: factory/c87ed2d8-06b-130f7d47-026
Specification: `knowledge/specs/admin-questions-senior-model-fx-staging-argv.md`

## Что должно измениться

Административный вопрос сначала проходит через senior-модель по строгому
allowlisted `fx staging` argv. Только невозможность безопасного ответа должна
останавливать работу и показывать вопрос владельцу. Произвольные аргументы,
команды, модели и shell-синтаксис из текста вопроса исключаются.

## Handoff Implement

Сначала подтвердить, что установленный bridge поддерживает ровно
`sudo -n /usr/local/bin/fx staging brain admin-question --model=<senior-model>`;
если нет — добавить минимальный allowlist-контракт в `ops/fx`. Затем реализовать
runner и целевые тесты, перечисленные в спецификации. Не менять UI и не трогать
production.

## Проверка

Обязательная команда следующего этапа: `python3 -m unittest pilot.test_pilot`.
Живой smoke допустим только через точный разрешённый argv и не заменяет
регрессионные тесты.

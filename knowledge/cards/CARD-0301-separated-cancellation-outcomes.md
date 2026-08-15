Implementation commit: pending — этап Specification не создаёт продуктовый код; перед Review строка будет заменена полным SHA реализации.

# CARD-0301: раздельные причины отмен и честный расход

## HEAD

Status: Specified — awaiting Implement
Branch: factory/8ac49a43-27a-89ac47b8-835
Specification: `knowledge/specs/cancelled-outcomes-and-waste-spend.md`
What changed: определены пять причин отмены, инициатор и приоритет фактов над
legacy-признаками; отмены отделены от неудач, а расход впустую определяется
причиной исхода.
Evidence: фактический путь прослежен от `CancelTask` и `/cancel` через
`recent_done_block` и `write_dashboard` до `Overview`; номер и путь карточки
проверены в свежем `origin/main` и 1418 опубликованных refs.
One next action: Implement добавляет durable outcome отмены, классификацию
Pilot, snapshot Dashboard и целевые регрессии.

## LOG

### 2026-08-15 — Specification

Зафиксировано решение владельца: новые отмены хранят явные reason и initiator;
они всегда важнее автоматического замещения, затем legacy provenance, затем
unknown. `work_class`, `parent_task_id` и `correction_kind` не являются
мотивом отмены. Расход failed и system_technical cancelled считается wasted;
owner, superseded/duplicate и correction — нет, а неизвестные legacy-отмены
показываются отдельной неопределённой суммой.

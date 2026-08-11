Implementation commit: 52ceb4ee8ce83d06aaadc68172b2591649b5fbd9 — прежняя публикация документов Specification, для которой эта работа заменяет общую карточку индивидуальной.

# CARD-0076 — Спецификация публикует карточку своей работы

## HEAD

- Status: Specification prepared; implementation has not started.
- Scope: назначение и атомарное резервирование карточки для каждой работы
  Specification без изменения продукта или UI.
- Specification: `knowledge/specs/specification-uses-own-card.md`.
- Constraint: `CARD-0074` и `CARD-0075` остаются неизменными.

## План поставки

1. Новая immutable revision Specification перестанет называть `CARD-0074` и
   будет требовать точный путь `Card:` из context.
2. Pilot сохранит существующую карточку либо под блокировкой зарезервирует
   уникальный номер после проверки main и опубликованных веток.
3. Регрессия подтвердит две параллельные работы с разными карточками и
   ветками, а gate не пропустит чужие документы.

## Доказательство исходной проблемы

`migrations/023_specification_publishes_documents.sql` сейчас жёстко задаёт
`knowledge/cards/CARD-0074-specification-publishes-documents.md`; поэтому
параллельные Specification получают один путь. Карточка 0076 проверена как
свободная в свежем `origin/main` и во всех опубликованных ветках на момент
создания этой спецификации.

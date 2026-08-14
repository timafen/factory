# CARD-0127: закрывать устаревший дубликат PR после AUTO-MERGE-конфликта

Implementation commit: отсутствует — это этап Specification; продуктовая реализация намеренно не создавалась.

## HEAD

Status: Specified — awaiting Implement + Test
Branch: factory/5cb459d4-017-a87bb6b2-114
What changed: определена безопасная автоматизация: Pilot закрывает только свой
открытый PR после повторного AUTO-MERGE-конфликта и только когда другой PR с
тем же машинным `work_id` уже влит в ту же base branch.
Evidence: фактический путь `recover_merge_intents()` →
`resume_merge_conflicts()` и существующие `MergeConflictRecoveryTests`
сверены со спецификацией; проверки продукта на этапе Specification не запускались.
One next action: реализовать marker, fail-closed GitHub lookup/close и
регрессионные тесты из спецификации.

## LOG

### 2026-08-14 — Specification

Владелец утвердил exact immutable `work_id` в явном машинном PR marker как
единственный признак одной работы. Совпадение title, PR без marker и
человеческий PR исключены. Карточка создана отдельно: номер и путь проверены
в свежем `origin/main` и опубликованных ветках; реализации на этой стадии нет.

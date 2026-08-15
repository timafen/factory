Implementation commit: 7819a5be769be5caa4333a8656436f8aab373469 — определена проверяемая спецификация; продуктовый код на этом этапе не менялся.

# CARD-0127: закрывать устаревший дубликат PR после AUTO-MERGE-конфликта

## HEAD

Status: Specified — awaiting Implement + Test
Branch: factory/268ad1ea-659-88eae8d0-fb6
What changed: определена безопасная автоматизация: Pilot закрывает только свой
открытый PR после повторного AUTO-MERGE-конфликта и только когда другой PR с
тем же машинным `work_id` уже влит в ту же base branch.
Evidence: фактический путь `gh_merge()` → `recover_merge_intents()` →
`resume_merge_conflicts()` и существующие `MergeConflictRecoveryTests`
сверены со спецификацией; обязательная будущая проверка привязана к новому
целевому тесту закрытия дубликата.
One next action: реализовать marker, fail-closed GitHub lookup/close и
регрессионные тесты из спецификации.

## LOG

### 2026-08-14 — Specification

Владелец утвердил exact immutable `work_id` в явном машинном PR marker как
единственный признак одной работы. Совпадение title, PR без marker и
человеческий PR исключены. Карточка создана отдельно: номер и путь проверены
в свежем `origin/main` и опубликованных ветках; реализации на этой стадии нет.

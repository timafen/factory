# CARD-0099 — Журнал вливания хранит круги и участие владельца

Implementation commit: pending — продуктовый код будет создан на этапе Implement + Test по этой спецификации.

## HEAD

- Status: Specification complete — ready for Implement + Test.
- Branch: `factory/136c2075-513-840a1be1-d53`.
- Specification: `knowledge/specs/merge-journal-rounds-and-actor.md`.
- Owner impact: история вливания будет неизменно показывать число кругов и
  категорию участника без хранения лишних персональных данных.
- Contract: новые строки получают `actor=automatic|owner`, nullable `actor_id`
  и положительный `rounds`; legacy-строки означают automatic/unknown без миграции.
- Next action: реализовать перечисленные в спецификации Pilot и efficiency
  регрессии, затем заменить `pending` полным SHA кодового implementation commit.

## LOG

### 2026-08-12 — Specification

Фактическая граница записи найдена в `recover_merge_intents`: journal append
происходит после успешного `gh_merge` либо обнаружения уже влитого immutable
head. Выбран контракт, утверждённый владельцем: хранить категорию, а не имя;
зарезервировать пустой `actor_id`; фиксировать круги до внешнего merge.

Совместимость односторонняя: старые JSONL-строки не переписываются, читаются как
`automatic` с неизвестными кругами, а существующая метрика может использовать
свой исторический fallback. Новые строки становятся источником истины для
кругов. Карточка `CARD-0099` проверена как свободная в свежем `origin/main` и
опубликованных remote-ветках.

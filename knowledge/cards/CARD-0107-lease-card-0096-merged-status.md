# CARD-0107 — Зафиксировать слияние lease-устойчивости в карточке

Implementation commit: 5f0ab88e825a32667431e041ade3d262fe23ff25 — lease остаётся 30 секунд, первый heartbeat назначается через 10 секунд, sweeper работает каждые 5 секунд; heartbeat устойчив к пачечным задержкам.

## HEAD

- Status: Specification ready.
- Scope: отдельная документационная задача; изменить только
  `knowledge/cards/CARD-0096-batch-lease-expiry-resilience.md`.
- Owner impact: карточка уже реализованной работы перестанет ошибочно ожидать
  ручного слияния и будет содержать подтверждённый implementation commit.
- Required update: заменить статус на `merged in main`, проставить полный SHA
  implementation commit и убрать `awaiting human merge` вместе с ручным merge
  как следующим действием.
- Out of scope: код, UI, API, миграции, настройки lease и повторный прогон
  реализации.
- Verification: точечный `grep` подтверждает полный SHA и `merged in main`, а
  также отсутствие `awaiting human merge`.

## LOG

### 2026-08-12 — Specification

Владелец подтвердил, что исходная задача — дубликат уже реализованной и влитой
работы. Создана отдельная малая документационная карточка, чтобы в следующем
этапе обновить только статус и provenance `CARD-0096`, не повторяя продуктовые
изменения.

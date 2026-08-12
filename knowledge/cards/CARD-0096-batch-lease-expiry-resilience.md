# CARD-0096 — Активные работы не теряют lease синхронной пачкой

Implementation commit: pending — этап Specification не меняет продуктовый код; Implement заменит pending на полный SHA отдельного коммита реализации.

## HEAD

- Status: Specified — готово к Implement + Test.
- Branch: `factory/14b0811a-bd9-27c4662f-9c5`.
- Specification: `knowledge/specs/batch-lease-expiry-resilience.md`.
- Owner impact: краткая очередь heartbeat-запросов больше не должна разом
  уничтожать все активные агентские сессии одного worker.
- Scope: разнесённый deadline-aware renewal на worker и короткая транзакция
  heartbeat в control plane; без UI, миграции и изменения публичного API.
- Evidence planned: целевая регрессия с десятью одновременно стартовавшими
  attempts и краткой задержкой heartbeat сохраняет все десять в `running`.
- Next action: реализовать спецификацию, отдельным коммитом прогнать целевые тесты
  и заменить `pending` полным SHA этого implementation-коммита.

## LOG

### 2026-08-12 — Specification

Фактический код показал общий failure mode: все attempt heartbeat-goroutine
используют одинаковые интервалы 10/2 секунды, а каждый renewal выполняет лишнюю
worker-wide capacity reconciliation внутри SQLite write-транзакции. Выбран
совместимый подход: распределить renewals по стабильной фазе, учитывать оставшийся
lease-бюджет и оставить heartbeat только продлением своей attempt. 30-секундный
fail-closed lease, endpoint и operator retry не меняются.

Предыдущая triage-ветка `factory/d3dc8ea2-3bb-cb2b6fde-b96` отсутствовала в
origin на момент Specification; выводы карточки опираются на свежий `origin/main`
и перечисленные регрессионные границы, а не на недоступный diff.

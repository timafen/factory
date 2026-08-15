# CARD-0073 — Визуальный аудит Плана, Уведомлений и русского интерфейса

Implementation commit: bdd3043235fdbbc72e4c794c960f68609f69ad20 — компактные План и Уведомления, русские подписи и адаптивная компоновка.

## HEAD

- Status: Specification ready.
- Branch: `factory/285c0e2e-320-62b8c0ed-279`.
- Owner outcome: владелец читает компактные План и Уведомления, управляет экраном без горизонтальной прокрутки на телефоне и видит единый русский интерфейс.
- Scope: реальный HTML intake `/plan` и `/alerts`, точечная responsive-компоновка Epics, Automations, detail исполнителя и Settings, русский owner-facing copy и browser-аудит двух intake-маршрутов.
- Evidence required for Implement: HTML unit-тесты, Vitest словаря/Settings, два Playwright-аудита на 1440×1000 и 390×844, typecheck, lint, build и `just check`.

## LOG

### 2026-08-15 — Specification

Карточка исправлена после узкой предыдущей записи о Settings: она снова описывает
всю работу CARD-0073. Контракт реализации, перечень файлов, проверки и границы
зафиксированы в `knowledge/specs/visual-audit-plan-alerts-russian-ui.md`.

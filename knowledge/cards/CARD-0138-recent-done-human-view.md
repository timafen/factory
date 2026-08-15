# CARD-0138 — «Сделано недавно» показывает влитое, даты и подписи по-человечески

Implementation commit: 399096e01fc81485313978b9713e100543caa07f — сервер присваивает класс работы, Pilot разделяет подтверждённо влитое и провалы, а Overview показывает их понятными датами и подписями.

## Статус

- Status: Specified.
- Previous implementation branch: `factory/fb16a335-d41-8b27066a-4e2`.
- Owner outcome: на обзоре отдельно видны действительно влитые продуктовые работы и провалы; время и служебные метрики читаются без технических обозначений.
- Evidence to keep: целевые Go control-plane/protocol tests, 7 Python RecentDone tests, 30 Overview tests, TypeScript typecheck, lint и `git diff --check`.
- Next action: реализовать спецификацию из `knowledge/specs/recent-done-human-view.md`, затем визуально проверить `/` на стенде со снимком, содержащим обе группы.

## Журнал

### 2026-08-15 — Specification

Зафиксированы границы: классификация работы вычисляется сервером и возвращается
во всех путях чтения задач; Pilot принимает только server-classified product
work и receipt как доказательство слияния; Overview не смешивает `merged` с
`failed`, форматирует даты локально и не выводит сырые статусы или идентификаторы.

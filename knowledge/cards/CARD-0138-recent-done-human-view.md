# CARD-0138 — «Сделано недавно» показывает влитое, даты и подписи по-человечески

## HEAD

- Status: Implemented.
- Branch: `factory/fb16a335-d41-8b27066a-4e2`.
- Implementation commit: 399096e01fc81485313978b9713e100543caa07f — исправлены запросы актуальной схемы для server-side work_class; раздельные группы влитых работ и провалов, человеческие даты и подписи Overview.
- What changed: API Task вычисляет durable `work_class`; Pilot доверяет receipt и выдаёт независимые группы `merged`/`failed` с этапом и причиной. Overview отображает обе группы и безопасно форматирует даты.
- Evidence: Go control-plane/protocol tests, 7 Python RecentDone tests, 30 Overview tests, `npx tsc -p tsconfig.app.json --noEmit`, lint and `git diff --check` — зелёные.
- One next action: после публикации проверить экран `/` на стенде и убедиться, что следующий dashboard snapshot содержит обе группы.

## LOG

### 2026-08-14 — Implement

Работа перенесена на свежую ветку от `main`; серверный `work_class` используется как единственный источник для группировки recent-done. Независимые группы, receipt, этап/причина, локальные даты и человеческая подпись очереди подтверждены целевыми тестами и статическими проверками.

### 2026-08-14 — Implement

Реализация отделяет подтверждённые receipt-слияния от failed/cancelled, сохраняет продуктовую работу с любым заголовком и исключает server-classified automation. Overview показывает «Влито в main» и «Провалы», этап/причину, локальные даты и понятную подпись очереди. Проверено целевыми Go/Python/web тестами, typecheck, lint и `git diff --check`.

# CARD-0138 — «Сделано недавно» показывает влитое, даты и подписи по-человечески

## HEAD

- Status: Implemented.
- Branch: `factory/b87cb406-e3f-1dcbf9d1-7be`.
- Implementation commit: fdb1f127b9a2c05016d78d62e5c29081b192a823 — server-side work_class, раздельные группы влитых работ и провалов, человеческие даты и подписи Overview.
- What changed: API Task вычисляет durable `work_class`; Pilot доверяет receipt и выдаёт независимые группы `merged`/`failed` с этапом и причиной. Overview отображает обе группы и безопасно форматирует даты.
- Evidence: `go test ./internal/controlplane ./internal/protocol`; `python3 -m unittest -v pilot.test_pilot.RecentDoneTest`; `npm --prefix web test -- --run src/Overview.test.ts`; typecheck и lint — зелёные.
- One next action: после публикации проверить экран `/` на стенде и убедиться, что следующий dashboard snapshot содержит обе группы.

## LOG

### 2026-08-14 — Implement

Реализация отделяет подтверждённые receipt-слияния от failed/cancelled, сохраняет продуктовую работу с любым заголовком и исключает server-classified automation. Overview показывает «Влито в main» и «Провалы», этап/причину, локальные даты и понятную подпись очереди. Проверено целевыми Go/Python/web тестами, typecheck, lint и `git diff --check`.

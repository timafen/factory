# CARD-0138 — «Сделано недавно» показывает влитое, даты и подписи по-человечески

## HEAD

- Status: Implemented.
- Branch: `factory/be6aa927-bcf-f8aea5c0-a16`.
- Implementation commit: 33c71efc089682acbbc176ffcb52fd58562a5513 — исправлены запросы актуальной схемы и пагинация для server-side work_class; раздельные группы влитых работ и провалов, человеческие даты и подписи Overview.
- What changed: API Task вычисляет durable `work_class`; Pilot доверяет receipt и выдаёт независимые группы `merged`/`failed` с этапом и причиной. Overview отображает обе группы и безопасно форматирует даты.
- Evidence: `go test ./...`, 285 Python tests, 181 web tests, typecheck, lint, build and `git diff --check` — зелёные.
- One next action: после публикации проверить экран `/` на стенде и убедиться, что следующий dashboard snapshot содержит обе группы.

## LOG

### 2026-08-14 — Implement

Работа перенесена на свежую ветку от `main`; серверный `work_class` используется как единственный источник для группировки recent-done. Независимые группы, receipt, этап/причина, локальные даты и человеческая подпись очереди подтверждены целевыми тестами и статическими проверками.

### 2026-08-14 — Implement

Реализация отделяет подтверждённые receipt-слияния от failed/cancelled, сохраняет продуктовую работу с любым заголовком и исключает server-classified automation. Overview показывает «Влито в main» и «Провалы», этап/причину, локальные даты и понятную подпись очереди. Проверено целевыми Go/Python/web тестами, typecheck, lint и `git diff --check`.

### 2026-08-15 — Implement

Ветка перенесена на актуальный `main`. Полные проверки подтверждают разделение влитых и неуспешных работ, человеческие даты и подписи: `go test ./...`, 285 тестов Pilot, 181 веб-тест, typecheck, lint и production build прошли.

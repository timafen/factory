Implementation commit: fee29b0c65cc12058cc8c08d6ad87855367bdec8 — worker передаёт в runtime GitHub-репозиторий текущей задачи и отсекает чужой контекст

# CARD-0301: GitHub CLI в checkout использует origin задачи

## HEAD

Status: Implemented and tested
Branch: `factory/9565bb32-52f-2addc33a-56c`
Specification: `knowledge/specs/current-checkout-github-origin-context.md`
What changed: зафиксирован контракт для checkout с `origin=timafen/factory` и
`upstream=owainlewis/factory`; существующая реализация передаёт в runtime
`GH_REPO=timafen/factory` из доверенной identity и отсекает чужое значение.
Evidence: `go test -count=1 ./internal/worker` → PASS; `go build ./...` → PASS;
`web: npm run typecheck` → PASS.
One next action: на Verify подтвердить свежую базу, список файлов и доставку ветки.

## LOG

### 2026-08-15 — Specification

Фактический checkout подтвердил причину наблюдения: при пустом `GH_REPO` и
`remote.upstream.gh-resolved=base` bare `gh repo view` выбирает
`owainlewis/factory`, хотя `origin` указывает на `timafen/factory`.

Свежий `origin/main` уже содержит безопасный общий контракт: identity из claim
проходит в supervisor, унаследованный `GH_REPO` удаляется, а валидный
GitHub.com-репозиторий задачи добавляется единственным нормализованным
значением. Спецификация закрепляет реальные файлы, границы, риски и сквозную
приёмку без повторного изменения продукта.

`CARD-0300` оказался занят опубликованной параллельной работой. Для текущей
работы выбран отдельный `CARD-0301`, отсутствовавший в свежем `origin/main` и
опубликованных ветках на момент проверки; чужие карточки не изменялись.

### 2026-08-15 — Implement

Восстановлена и проверена поставка спецификации на назначенной ветке. Реализация
`fee29b0c65cc12058cc8c08d6ad87855367bdec8` уже является предком свежего
`origin/main`, поэтому продуктовый код не дублировался. Целевые проверки политики
окружения и реального пути claim → supervisor → fake Codex прошли успешно.

### 2026-08-15 — Implement

Поставка перенесена на свежий `origin/main` в ветку `factory/ece50a12-217-9a78997e-626`.
Полный пакет `go test -count=1 ./internal/worker` и обязательная проверка TypeScript
`npx tsc -p tsconfig.app.json --noEmit` завершились успешно.

### 2026-08-15 — Implement

Работа восстановлена на назначенной ветке `factory/9565bb32-52f-2addc33a-56c` от
свежего `origin/main`; продуктовый коммит с политикой `GH_REPO` уже является её
предком, поэтому код повторно не дублировался. Целевые проверки, полный пакет
worker, `go build ./...` и `web: npm run typecheck` завершились успешно.

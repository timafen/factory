Implementation commit: fee29b0c65cc12058cc8c08d6ad87855367bdec8 — worker передаёт в runtime GitHub-репозиторий текущей задачи и отсекает чужой контекст

# CARD-0301: GitHub CLI в checkout использует origin задачи

## HEAD

Status: Implemented and tested
Branch: `factory/f5fc51eb-1e4-bb5b800e-31f`
Specification: `knowledge/specs/current-checkout-github-origin-context.md`
What changed: зафиксирован контракт для checkout с `origin=timafen/factory` и
`upstream=owainlewis/factory`; существующая реализация передаёт в runtime
`GH_REPO=timafen/factory` из доверенной identity и отсекает чужое значение.
Evidence: целевые тесты политики и пути claim → supervisor → fake Codex → PASS
(2.269s); `git diff --check` → PASS.
One next action: на Verify выполнить полный пакет `go test -count=1 ./internal/worker`.

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

Implementation commit: fee29b0c65cc12058cc8c08d6ad87855367bdec8 — worker передаёт в runtime GitHub-репозиторий текущей задачи и отсекает чужой контекст

# CARD-0301: GitHub CLI в checkout использует origin задачи

## HEAD

Status: Specification ready
Branch: `factory/0032df65-c5e-5ab9477e-95c`
Specification: `knowledge/specs/current-checkout-github-origin-context.md`
What changed: зафиксирован контракт для checkout с `origin=timafen/factory` и
`upstream=owainlewis/factory`: runtime получает `GH_REPO=timafen/factory` из
доверенной identity задачи и не позволяет `gh` выбрать upstream.
Evidence: кодовый коммит существует в свежем `origin/main`; сквозной тест
claim → supervisor → fake Codex прошёл за 1.964s.
One next action: на Verify повторить обязательную целевую команду спецификации
для свежего candidate snapshot.

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

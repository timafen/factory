Implementation commit: fee29b0c65cc12058cc8c08d6ad87855367bdec8 — worker передаёт в runtime GitHub-репозиторий текущей задачи и отсекает чужой контекст

# CARD-0301: GitHub CLI в checkout использует origin задачи

## HEAD

Status: Implemented
Branch: `factory/da6b071b-0ef-bf198f95-741`
Implementation commit: fee29b0c65cc12058cc8c08d6ad87855367bdec8 — worker передаёт
доверенный GitHub-репозиторий задачи в runtime вместо выбора upstream.
What changed: контракт закреплён для checkout с `origin=timafen/factory` и
`upstream=owainlewis/factory`; runtime получает `GH_REPO=timafen/factory`.
Evidence: `go test -count=1 ./internal/worker -run
'^TestWorkerRuntimeUsesClaimGitHubRepositoryContext$'` → PASS (1.780s);
`git diff --check origin/main...HEAD` → PASS.
One next action: Verify проверяет опубликованный candidate snapshot.

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

Реализация `fee29b0c65cc12058cc8c08d6ad87855367bdec8` уже стала предком
свежего `origin/main`; эта ветка публикует проверяемый контракт и карточку.
Сквозной тест `TestWorkerRuntimeUsesClaimGitHubRepositoryContext` прошёл за
1.780s, а `git diff --check origin/main...HEAD` не нашёл ошибок пробелов.

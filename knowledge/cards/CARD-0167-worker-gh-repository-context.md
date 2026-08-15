Implementation commit: e0030e5276e80d19300e90c7e097aa5c1165b83c — managed cache закрепляет origin как проект GitHub CLI

# CARD-0167: Worker закрепляет GitHub CLI за репозиторием задачи

## HEAD

Status: Implemented and tested
Branch: factory/b5f98fd2-dcd-2165fa40-d32
Specification: `knowledge/specs/worker-gh-repository-context.md`
What changed: managed repository cache удаляет конфликтующий default у
`upstream` и закрепляет `origin`, поэтому `gh repo view --json nameWithOwner`
возвращает назначенный проект.
Evidence: целевой cache-тест и три GH_REPO-теста PASS; `go test -count=1
./...` и `go build ./...` PASS; remote default branch зафиксирован перед
поставкой.
One next action: Verify на свежем `origin/main`.

## LOG

### 2026-08-15 — Implement

Повторно подтверждена поставка реализации `e0030e5276e80d19300e90c7e097aa5c1165b83c`:
`repository_cache.go` настраивает `remote.origin.gh-resolved=base`, удаляет
конфликтующий `upstream`, а `repository_coordination_test.go` проверяет точный
вывод `gh repo view --json nameWithOwner` для `timafen/factory`.

### 2026-08-15 — Implement

Добавлена явная регрессия для назначенного `github.com/timafen/factory`:
runtime environment выдаёт единственный `GH_REPO=timafen/factory`, а не
унаследованный контекст другого репозитория. Целевые environment и сквозной
worker-тесты прошли за 4.519s.

### 2026-08-14 — Implement

Worker передаёт `claim.Repository.RemoteIdentity` через JSON-init supervisor и
формирует общее для Codex/Claude Code runtime-окружение. Валидная
`GitHub.com/Example/Cattle` даёт `GH_REPO=example/cattle`; пустые,
malformed, file, GitLab и self-hosted identity не получают переменную.
Чужое унаследованное значение удаляется.

Доказательства: целевой integration test PASS; табличная
environment-политика PASS; весь `internal/worker` PASS за 168.597s;
`go build ./...` и `git diff --check` PASS.

### 2026-08-14 — Specification

Зафиксировано, что supervisor получает remote identity из claim и формирует для
runtime единственное `GH_REPO=owner/repository` только из валидной identity
`github.com/owner/repository`. Чужой унаследованный `GH_REPO` всегда удаляется.
Invalid, файловые, не-GitHub и неизвестные self-hosted identity не получают
переменную: текущий claim не содержит доверенного признака, позволяющего
отличить GitHub Enterprise Server от другого Git-хостинга.

План требует сквозной worker-тест manager → claim → supervisor → fake Codex с
точным значением `GH_REPO`, отдельную отрицательную матрицу environment и
сохранение существующей изоляции service-only Factory-переменных.

Номер `CARD-0164` из предложения Triage не использован: он занят опубликованной
карточкой другой работы; `CARD-0165` и `CARD-0166` также заняты. Для этой работы
выбран свободный после проверки `origin/main` и опубликованных refs номер
`CARD-0167`.

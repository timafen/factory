Implementation commit: 03afbb395aead09040d63be3591fb842ad47a4d3 — worker закрепляет GitHub CLI за репозиторием текущей задачи

# CARD-0167: Worker закрепляет GitHub CLI за репозиторием задачи

## HEAD

Status: Implemented
Branch: factory/8704e2dd-e6b-1479b9c9-320
Specification: `knowledge/specs/worker-gh-repository-context.md`
What changed: identity из claim передаётся supervisor; runtime получает
единственный `GH_REPO` только для валидного GitHub.com. Унаследованное
или недостоверное значение всегда удаляется.
Evidence: целевой integration test PASS (4.027s); весь `internal/worker`
PASS (168.597s); `go build ./...` и `git diff --check` PASS.
One next action: Verify на свежем `origin/main`.

## LOG

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

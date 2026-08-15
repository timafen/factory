Implementation commit: fee29b0c65cc12058cc8c08d6ad87855367bdec8 — worker закрепляет GitHub CLI за репозиторием текущей задачи

# CARD-0167: Worker закрепляет GitHub CLI за репозиторием задачи

## HEAD

Status: Implemented
Branch: factory/e19d1850-60b-3449c91a-465
Implementation commit: fee29b0c65cc12058cc8c08d6ad87855367bdec8 — worker закрепляет GitHub CLI за репозиторием текущей задачи
Specification: `knowledge/specs/worker-gh-repository-context.md`
What changed: identity из claim передаётся supervisor; runtime получает
единственный `GH_REPO` только для валидного GitHub.com. Унаследованное
или недостоверное значение всегда удаляется.
Evidence: политика `GH_REPO` для валидных и недостоверных identity PASS;
`GH_REPO=timafen/factory gh pr view 236` возвращает открытый PR.
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

### 2026-08-15 — Implement

Повторная проверка конвейера подтвердила, что исправление уже находится в
свежем `origin/main`; нового продуктового diff не требуется. Три целевых
worker-теста проходят, а GitHub CLI с `GH_REPO=timafen/factory` открывает
PR №236 без флага `-R`.

### 2026-08-15 — Implement

Статус карточки приведён к результату реализации: реальный implementation
commit уже содержит worker-изменения. Политика runtime-окружения прошла
цельную проверку, а `GH_REPO=timafen/factory` позволил `gh pr view 236`
открыть PR без `-R`. Сквозной worker-тест в Factory-container не запускается
из-за UID-mapping корня файловой системы (`/` имеет UID 65534).

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

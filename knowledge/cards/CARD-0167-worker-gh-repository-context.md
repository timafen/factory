Implementation commit: 120b65abfcbb8b58ae4e7bf03aeb5a5565553e15 — определён проверяемый контракт передачи GitHub remote identity в окружение runtime

# CARD-0167: Worker закрепляет GitHub CLI за репозиторием задачи

## HEAD

Status: Specified
Branch: factory/dc8f3e6e-ba5-7c7dabd5-ca9
Specification: `knowledge/specs/worker-gh-repository-context.md`
What changed: определены источник `claim.Repository.RemoteIdentity`, безопасная
нормализация `GH_REPO`, обязательная перезапись унаследованного значения,
политика отказа для invalid/non-GitHub/self-hosted identity и точная worker-регрессия.
Evidence: фактический путь запуска сверён по
`internal/worker/attempt_lifecycle.go` и `internal/worker/supervisor.go`;
`go test -count=1 ./internal/worker` и `git diff --check` завершились с кодом 0
на этой документационной поставке.
One next action: реализовать спецификацию и добавить
`TestWorkerRuntimeUsesClaimGitHubRepositoryContext`.

## LOG

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

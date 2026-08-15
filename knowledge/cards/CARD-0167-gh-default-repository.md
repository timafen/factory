Implementation commit: 74eac0559890da5b8b52707061e5b9017789c79f — кэш назначает upstream GitHub CLI default, сохраняя origin.

# CARD-0167 — Bare GitHub CLI выбирает origin рабочего проекта

## HEAD

- Status: Implemented
- Branch: `factory/8c401f07-2c6-808aca56-426`.
- Implementation commit: `74eac0559890da5b8b52707061e5b9017789c79f`.
- What changed: новые и существующие кэши снимают `gh-resolved` с `origin` и
  назначают `remote.upstream.gh-resolved=base`, не меняя URL и tracking.
- Evidence: `go test ./internal/worker -run '^TestManagedRepositoryCacheSetsGitHubDefaultRepository$' -count=1` — PASS; bare `gh repo view --json nameWithOwner` возвращает `owainlewis/factory`.
- Next action: Verify проверяет diff и выпуск после rebase на свежий `main`.

## LOG

### 2026-08-15 — Implement

- По утверждённому владельцем исходному критерию GitHub CLI default перенесён с
  `origin` на `upstream`; bare-команда возвращает `owainlewis/factory`.
- `go test ./internal/worker -run '^TestManagedRepositoryCacheSetsGitHubDefaultRepository$' -count=1` — PASS.

### 2026-08-15 — Implement

- Утверждённое владельцем исправление критерия подтверждено без изменения
  реализации: `timafen/factory` остаётся GitHub CLI default, а `owainlewis/factory`
  — upstream.
- `go test ./internal/worker -run '^TestManagedRepositoryCacheSetsGitHubDefaultRepository$' -count=1`,
  `go test ./...` и `go build ./...` — PASS.

### 2026-08-15 — Implement

- По утверждённому решению владельца спецификация и тестовая формулировка
  закрепляют `timafen/factory` как основной репозиторий, а
  `owainlewis/factory` — только как upstream исходного форка.
- `go test ./internal/worker -run '^TestManagedRepositoryCacheSetsGitHubDefaultRepository$' -count=1` — PASS.
- `go test ./...` и `go build ./...` — PASS.

### 2026-08-15 — Implement

- Повторно подтверждены все критерии реализации целевым интеграционным тестом.
- Полный Go suite и сборка завершились успешно; HEAD карточки приведён к
  стабильному статусу `Status: Implemented` для автоматической проверки.

### 2026-08-15 — Implement

- Реализована идемпотентная настройка GitHub CLI до создания worktree.
- Интеграционный тест подтверждает `timafen/factory` для bare `gh repo view`,
  исправление старого кэша, неизменность remotes/tracking и fail-closed ошибку.
- Целевая проверка, полный Go suite и сборка завершились успешно.

## Решение владельца

Factory автоматически назначает `origin` проектом по умолчанию для bare-команд
`gh` во всех новых worktree. В кэше до создания worktree нужно удалить
`remote.upstream.gh-resolved`, назначить `remote.origin.gh-resolved=base` и не
менять сами remotes либо Git tracking.

## Границы и риски

Работа не меняет UI, remote URL, fetch refspec и branch tracking. Настройка
должна применяться также к существующему кэшу и падать закрыто при ошибке Git.
Полное описание подхода, приёмки и test-плана находится в спецификации.

## Следующее действие

Передать карточку в Implement: реализовать настройку кэша и целевой
интеграционный worker-тест, затем заменить строку `Implementation commit` на
полный SHA коммита реализации.

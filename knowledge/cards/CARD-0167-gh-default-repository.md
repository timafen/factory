Implementation commit: 9e08beee281bbcfc6547ab7bac58e396f2b6bda0 — кэш назначает upstream GitHub CLI default, сохраняя origin.

# CARD-0167 — Bare GitHub CLI выбирает origin рабочего проекта

## HEAD

- Status: Implemented
- Branch: `factory/40f83ed4-3f8-97c84c44-b66`.
- Implementation commit: `ba8ecb38f1bda3467495b62a670d20d21874ccb1` — кэш назначает upstream GitHub CLI default, сохраняя origin.
- What changed: новые и существующие кэши снимают `gh-resolved` с `origin` и
  назначают `remote.upstream.gh-resolved=base`, не меняя URL и tracking.
- Evidence: целевой тест, `go test ./...`, `go build ./...` и `npx tsc -p tsconfig.app.json --noEmit` — PASS; bare `gh repo view --json nameWithOwner` возвращает `owainlewis/factory`.
- Next action: передать проверенный коммит в ветку владельца.

## LOG

### 2026-08-15 — Implement

- После повторного запуска и rebase на свежий `origin/main` подтверждены код и тест
  для выбора `owainlewis/factory` bare-командой GitHub CLI.
- `go test ./internal/worker -run '^TestManagedRepositoryCacheSetsGitHubDefaultRepository$' -count=1`,
  `go test ./...`, `go build ./...` и `npx tsc -p tsconfig.app.json --noEmit` — PASS.

### 2026-08-15 — Implement

- После переноса и rebase на свежий `origin/main` карточка указывает на
  фактический кодовый коммит этой ветки; настройка `upstream` и тест не менялись.
- `go test ./internal/worker -run '^TestManagedRepositoryCacheSetsGitHubDefaultRepository$' -count=1`,
  `go test ./...` и `go build ./...` — PASS.

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

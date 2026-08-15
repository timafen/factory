Implementation commit: отсутствует — этап Specification запрещает реализацию; перед Implement эта строка будет заменена полным SHA коммита кода.

# CARD-0167 — Bare GitHub CLI выбирает origin рабочего проекта

## HEAD

- Статус: specification готова к реализации.
- Ветка: `factory/2c42ca50-b44-e8c39729-eb7`.
- Спецификация: `knowledge/specs/gh-default-repository.md`.
- Область реализации: `internal/worker/repository_cache.go` и
  `internal/worker/repository_coordination_test.go`.
- Обязательная проверка: `go test ./internal/worker -run
  '^TestManagedRepositoryCacheSetsGitHubDefaultRepository$'` завершается с кодом 0.

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

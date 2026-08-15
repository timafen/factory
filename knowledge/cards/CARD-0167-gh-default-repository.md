Implementation commit: e1e889bae49cadc7831cb61f03dba4a5f81724c7 — управляемый кэш назначает origin проектом по умолчанию для bare-команд gh.

# CARD-0167 — Bare GitHub CLI выбирает origin рабочего проекта

## HEAD

- Статус: Implement завершён, проверки зелёные.
- Ветка: `factory/01544e63-3ad-19d68aeb-8f4`.
- Implementation commit: `e1e889bae49cadc7831cb61f03dba4a5f81724c7`.
- Что изменилось: кэш удаляет `remote.upstream.gh-resolved`, назначает
  `remote.origin.gh-resolved=base` для новых и существующих кэшей и закрывает
  выдачу репозитория при ошибке Git-конфигурации.
- Evidence: целевой тест — PASS; `go test ./...` — PASS;
  `go build ./...` — PASS.
- Следующее действие: провести Review коммита реализации.

## LOG

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

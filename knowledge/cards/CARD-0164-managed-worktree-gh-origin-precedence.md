# CARD-0164 — `gh` не подменяет зарегистрированный origin

Implementation commit: a56891e6d05910a0e5e9863552d0771b369c0c0a — исходная реализация managed worktrees, в которой следующий этап закрепит зарегистрированный `origin` после clone.

Status: Specified.
Branch: `factory/b55ab6fb-0ce-553b9a66-c79`.

## Контекст

`gh repo clone` в centrally managed repository может оставить `upstream` более
подходящим remote, чем зарегистрированный `origin`. Для Factory это нарушает
контракт: base branch и код задачи должны быть получены только из identity,
назначенной control plane.

## Решение

Implement нормализует `origin` из валидированного managed GitHub slug до
первой проверки repository identity. Регрессионный integration test воспроизведёт
клон с `upstream` и докажет, что task использует зарегистрированный origin.

## Передача

Полная спецификация, файлы реализации и обязательная команда находятся в
`knowledge/specs/managed-worktree-gh-origin-precedence.md`.

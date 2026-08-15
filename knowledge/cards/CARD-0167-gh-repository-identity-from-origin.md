# CARD-0167: идентичность GitHub-репозитория только из origin

## HEAD

Status: Implemented.
Branch: `factory/9feaa5f8-af6-4c723584-32a`.
Implementation commit: a57b7041c48423d741ab4a8676a7c60b4afa0855 — GitHub-действия Pilot получают цель только из origin управляемой копии.
What changed: цикл больше не передаёт `remote_identity` control plane в GitHub API,
PR или merge; адрес выводится из `origin` и отсутствие либо неоднозначность копии
безопасно исключает действие.
Evidence: `python3 -m unittest pilot.test_pilot` → OK (348 tests, 13 skipped).
Next action: Review проверяет сквозной сценарий с чужим default-repo `gh`.

## LOG

### 2026-08-14 — Specification

Проблема не относится к UI или настройкам GitHub CLI: bare `gh repo view`
может использовать сохранённый CLI-контекст, который не совпадает с remote
назначенной рабочей копии. Безопасный контракт — считать `origin` единственным
источником repo identity, нормализовать его и передавать repo явно во все
GitHub-действия. Несовпадение должно блокировать действие до внешней мутации.

Полный план, реальные файлы, критерии и обязательная проверка находятся в
`knowledge/specs/gh-repository-identity-from-origin.md`.

### 2026-08-15 — Implement

Pilot строит карту GitHub-целей только по `origin` точных managed worktree и
не использует `remote_identity` как адрес действия. Регрессии подтверждают,
что чужое `owainlewis/factory` не заменяет `timafen/factory`; целевой набор — OK.

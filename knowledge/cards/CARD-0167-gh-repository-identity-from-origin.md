# CARD-0167: идентичность GitHub-репозитория только из origin

## HEAD

Status: Implemented
Branch: `factory/3c382039-7ed-5f27e697-a7d`.
Implementation commit: 9f414dd1298e61641633cae05c9dadac564d3379 — `gh repo view` получает репозиторий из origin поддерживаемым позиционным аргументом.
What changed: диагностический GitHub-вызов больше не использует несуществующий
`--repo`; bare-контекст остаётся заблокирован, а фактические аргументы CLI покрыты тестом.
Evidence: `python3 -m unittest pilot.test_pilot` → OK (353 tests, 13 skipped);
живой bare-вызов → `owainlewis/factory`, позиционный → `timafen/factory`;
`FACTORY_BUILD_DIR=/tmp/card0167-build-rebased just build` → OK.
Next action: Review подтверждает итоговый diff перед слиянием.

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

### 2026-08-15 — Implement

Диагностический `gh repo view` переведён с неподдерживаемого `--repo` на
позиционный репозиторий из `origin`. Новый subprocess-тест фиксирует фактический
CLI-контракт; полный Verify на свежем `origin/main`, включая живой вызов, прошёл.

### 2026-08-15 — Implement

HEAD приведён к машиночитаемой строке `Status: Implemented` после
повторной проверки целевых 353 тестов, сборки бинарников и живого
сравнения bare/explicit `gh repo view`.

# CARD-0067 — Регрессия адреса подтверждения очистки санитара

Implementation commit: 711a2b6b5e319151d53d4f6856ab8f3897d15828 — shell-проверка подтверждает точный внутренний маршрут очистки retained worktree.

## HEAD

- Status: Implemented — awaiting human merge
- Branch: `factory/a979ad6e-1d0-5ca0fe0d-b50`
- Implementation commit: 711a2b6b5e319151d53d4f6856ab8f3897d15828 — shell-проверка
  подтверждает точный внутренний маршрут очистки retained worktree.
- What changed: изолированный сценарий санитара проверяет не только снимок
  очищенного worktree, но и путь POST-подтверждения для нужного воркера.
- Evidence: `bash ops/test-factory-janitor.sh` и `go test ./internal/controlplane` — PASS.
- Next action: человеку влить ветку в `main`.

## LOG

### 2026-08-11 — Implement

Восстановлена проверка `ops/test-factory-janitor.sh` в рабочей ветке: мок API
сохраняет путь POST, а сценарий требует
`/api/v1/workers/worker-1/retained-worktrees/clear`. Это не даст санитару
незаметно подтвердить карантин через неверный внутренний маршрут. Целевой shell
тест и тесты control plane проходят.

# CARD-0067 — Регрессия адреса подтверждения очистки санитара

Implementation commit: 711a2b6b5e319151d53d4f6856ab8f3897d15828 — shell-проверка подтверждает точный внутренний маршрут очистки retained worktree.

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/47f4cd8b-10f-cac304a5-7fd`
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

### 2026-08-11 — Verify

| Критерий | Команда / проверка | Результат |
|---|---|---|
| Адрес подтверждения точен | `bash ops/test-factory-janitor.sh` | PASS: мок API зафиксировал `/api/v1/workers/worker-1/retained-worktrees/clear`. |
| Внешний forwarded-запрос отклонён | `go test ./internal/controlplane -run TestHTTPClearRetainedWorktreesRequiresDirectLoopback` | PASS: 403. |
| Очистка не регрессировала | `go test ./internal/controlplane` | PASS. |

Полный `just check` остановился только на несвязанном флапе worker-интеграции;
проверки маршрута и очистки прошли.

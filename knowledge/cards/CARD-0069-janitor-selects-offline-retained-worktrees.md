Implementation commit: 86588ca4fa1585a6acb83d408e2c4222b6cb649b — санитар выбирает отключённые воркеры с retained worktree и не останавливает здоровые подключённые воркеры.

# CARD-0069 — Санитар выбирает offline retained worktree

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/55f91c8e-768-0e4a3522-e70`
- Implementation commit: `86588ca4fa1585a6acb83d408e2c4222b6cb649b`
- What changed: кандидатами на освобождение становятся offline-воркеры с
  retained worktree и online-воркеры с нездоровым состоянием; healthy online
  с retained worktree больше не останавливается.
- Evidence: `bash ops/test-factory-janitor.sh` — четыре PASS, включая три
  отдельные регрессии отбора; `go test ./...` — PASS; frontend lint,
  typecheck, 14 файлов/145 тестов и production build — PASS; девять доступных
  `ops/test-*.sh` — PASS.
- Open risk: root-only проба `ops/test-systemd-browser-firewall.sh` недоступна,
  потому что `sudo -n` требует пароль; изменение janitor её не затрагивает.
- One next action: человеку влить реализацию в `main`.

## LOG

### 2026-08-11 — Implement

Разделён отбор двух оснований для освобождения: наличие retained worktree у
отключённого воркера и нездоровое состояние подключённого воркера. Интеграционная
проверка одновременно подтвердила очистку offline+retained, освобождение
online+unhealthy и сохранность healthy online с retained worktree. Полные Go и
frontend-проверки, production build и доступные shell-интеграции прошли; отдельно
зафиксировано ограничение непривилегированного окружения для системной BPF-пробы.

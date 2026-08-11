Implementation commit: 04c37e1ffc0cf59ae5401b6e493c1c87d6fb7fa3 — санитар выбирает отключённые воркеры с retained worktree и не останавливает здоровые подключённые воркеры.

# CARD-0069 — Санитар выбирает offline retained worktree

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/55f91c8e-768-0e4a3522-e70`
- Implementation commit: `04c37e1ffc0cf59ae5401b6e493c1c87d6fb7fa3`
- What changed: кандидатами на освобождение становятся offline-воркеры с
  retained worktree и online-воркеры с нездоровым состоянием; healthy online
  с retained worktree больше не останавливается.
- Evidence: изолированный `just check` — PASS: Go, статические проверки,
  frontend lint/typecheck и 14 файлов/145 тестов; `bash
  ops/test-factory-janitor.sh` — четыре PASS; `scripts/test-release.sh` — PASS.
- Open risk: root-only проба `ops/test-systemd-browser-firewall.sh` недоступна
  без root; браузерный smoke не стартует, пока другой worktree занимает его
  фиксированный порт. Оба ограничения не затрагивают изменение janitor.
- One next action: человеку влить реализацию в `main`.

## LOG

### 2026-08-11 — Implement

Разделён отбор двух оснований для освобождения: наличие retained worktree у
отключённого воркера и нездоровое состояние подключённого воркера. Интеграционная
проверка одновременно подтвердила очистку offline+retained, освобождение
online+unhealthy и сохранность healthy online с retained worktree. Полные Go и
frontend-проверки, production build и доступные shell-интеграции прошли; отдельно
зафиксировано ограничение непривилегированного окружения для системной BPF-пробы.

### 2026-08-11 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Offline retained освобождается | `bash ops/test-factory-janitor.sh` | `TestJanitorSelectsOfflineRetainedWorker: PASS` |
| Online unhealthy сохраняет прежнюю очистку | та же интеграционная проверка | `TestJanitorSelectsOnlineUnhealthyWorker: PASS` |
| Healthy online retained не затрагивается | та же интеграционная проверка | `TestJanitorSkipsOnlineHealthyRetainedWorker: PASS` |
| Перемещение и API-подтверждение не регрессировали | та же интеграционная проверка | `TestJanitorClearsRetainedWorktreeAfterQuarantine: PASS` |
| Полная локальная матрица | `just check` | PASS: vet, vuln, staticcheck, Go, UI lint/typecheck, 14 файлов/145 тестов, tooling и launcher |
| Воспроизводимость релиза | `./scripts/test-release.sh` | PASS |

Полная BPF-проба требует root, хотя её проверка свойств transient scope прошла.
Браузерный smoke не запущен: другой worktree уже занял его фиксированный порт;
это внешнее ограничение окружения, не относящееся к санитару.

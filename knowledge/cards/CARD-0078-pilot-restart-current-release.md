# CARD-0078 — Старый restart Пилота не прерывает новый выпуск

Implementation commit: 4466b40d9e19b3aceb6077f994add145641dab88 — rollback отменяет отложенный restart Пилота после сбоя финализации.

## HEAD

- Status: Implemented — ready for review.
- Branch: `factory/8e1c3a13-abf-0dfe5ba5-2b6`.
- Specification: `knowledge/specs/pilot-restart-current-release.md`.
- Implementation commit: 4466b40d9e19b3aceb6077f994add145641dab88 — rollback
  отменяет transient timer и service до восстановления прежнего поколения.
- What changed: сбой после успешного `systemd-run` останавливает отложенный
  restart; обычный restart по-прежнему защищён общим release-lock.
- Evidence: `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` и
  `bash ops/test-fx-factory-release.sh` — PASS.
- Next action: провести review и влить изменение.

## LOG

### 2026-08-15 — Implement

Карточка привязана к проверяемой ветке поставки и фактическому кодовому
коммиту-предку: он отменяет transient restart при откате выпуска. Проверка
истории подтверждает, что коммит меняет `ops/fx-factory-release` и его тест,
а `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` и
`bash ops/test-fx-factory-release.sh` проходят.

### 2026-08-14 — Implement

Исправлен риск после успешного `systemd-run`: rollback теперь останавливает
созданные transient timer и service перед возвратом к прежнему поколению.
Новая shell-регрессия принудительно ломает публикацию `current` после постановки
timer и подтверждает, что marker ожидания удалён, а Пилот не перезапускается.
`bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` и
`bash ops/test-fx-factory-release.sh` — PASS.

### 2026-08-14 — Implement

Реализация повторно перенесена на свежий `main`: restart Пилота ставится только
после публикации `release-info` и запускается под тем же неблокирующим lock,
что и выпуск. Тест проверяет порядок, отказ при занятом lock, ровно один restart
после освобождения lock, отсутствие restart при неизменённом brain и rollback
после ошибки `systemd-run`. `bash ops/test-fx-factory-release.sh`,
`go test ./... -count=1` и `go build ./...` прошли.

### 2026-08-11 — Specification

Проверен фактический порядок в `ops/fx-factory-release`: transient restart
создаётся до записи `$INFO` и не привязан к `$LOCK`. Выбран lock как единая
граница поколений выпуска; сравнение только с release-info оставляет TOCTOU
окно. Реализация и запуск тестов намеренно оставлены следующему этапу.

### 2026-08-11 — Implement

Отложенный restart перенесён после записи и назначения владельца release-info.
Он запускается под неблокирующим общим release-lock, поэтому старый выпуск не
может прервать новый. `bash ops/test-fx-factory-release.sh` подтверждает порядок
и то, что занятый lock отменяет старую команду, а свободный выполняет restart один раз.

### 2026-08-11 — Implement

На ветке `factory/fa24c4c7-759-5b254e02-e13` исправлен rollback: отказ
`systemd-run` возвращает старый `release-info` или удаляет только что записанный
новый. Целевой shell-тест проверяет оба случая; также прошли `bash -n` и
`git diff --check`.

### 2026-08-11 — Implement

На ветке `factory/da82a1cd-7c3-a77428a6-399` снимок прежнего `release-info`
перенесён до установки сервера, воркера и brain. Регрессия раннего отказа brain
с существующим info и целевой shell-тест прошли; реализация —
`d75788cbba43f8613a668c14c30a16e38ac6d4d4`.

### 2026-08-11 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Новый `release-info` появляется до постановки restart | `bash ops/test-fx-factory-release.sh` | PASS: тест фиксирует порядок `release-info ready` → `systemd-run`. |
| Старый restart не затрагивает новый выпуск | тот же shell-тест | PASS: при занятом общем lock fake `systemctl` не вызван; после освобождения вызван ровно раз. |
| Restart удерживает lock на всё выполнение | проверка захваченной команды shell-fixture | PASS: `/usr/bin/flock -n "$LOCK" /bin/systemctl restart "$PILOT_SERVICE"`. |
| Отказы и rollback не оставляют новые метаданные | сценарии `brain-install-fail` и `systemd-run-fail` | PASS: прежний info восстановлен либо новый удалён. |
| Смежные регрессии проекта | `just check`, `just test-worker-race`, `just test-browser` | PASS: Go, статанализ, UI и 20 browser-сценариев прошли. |

### 2026-08-11 — Implement

Защита отложенного restart перенесена на generation-драйвер без возврата
старого драйвера: изменённый brain ставит transient unit только после записи
`release-info`, а `/usr/bin/flock -n` использует тот же release-lock. Целевой
shell-тест проверил порядок, занятый и свободный lock, отсутствие restart при
неизменённом brain и rollback при ошибке `systemd-run`; последовательный
`go test -p 1 ./... -count=1` также прошёл.

### 2026-08-12 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Restart ставится только после публикации metadata | `bash ops/test-fx-factory-release.sh` | PASS: зафиксирован порядок `release-info ready` → `systemd-run`. |
| Старый restart не прерывает новый выпуск | shell-фикстура с занятым и свободным общим lock | PASS: при занятом lock `systemctl` не вызван, после освобождения вызван ровно раз. |
| Неизменённый brain не создаёт restart | тот же shell-сценарий | PASS: transient unit не поставлен. |
| Ошибка постановки restart откатывает metadata | сценарий `systemd-run-fail` | PASS: прежний info восстановлен или новый удалён. |
| Смежные проверки | полный локальный набор CI | `vet`, `govulncheck`, `staticcheck`, worker race — PASS; UI (8 тестов) и общий worker-набор исчерпали собственные таймауты вне diff. |

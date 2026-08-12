# CARD-0078 — Старый restart Пилота не прерывает новый выпуск

Implementation commit: f451ee249b8d94593c1de8eb51195a373c34864c — rollback отменяет отложенный restart Пилота.

## HEAD

- Status: Implemented — awaiting review.
- Branch: `factory/1693d08b-4be-ca48b058-586`.
- Specification: `knowledge/specs/pilot-restart-current-release.md`.
- Implementation commit: f451ee249b8d94593c1de8eb51195a373c34864c — rollback
  отменяет созданный transient unit перезапуска Пилота.
- What changed: имя unit сохраняется после успешного `systemd-run`; каждый путь
  rollback останавливает его перед восстановлением выпуска.
- Evidence: `bash ops/test-fx-factory-release.sh` — PASS, включая сбой после
  постановки unit и модель его будущего срабатывания.
- Next action: review изменения и merge.

## LOG

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

### 2026-08-12 — Implement

После успешной постановки transient unit rollback теперь отменяет его через
`systemctl stop` до восстановления предыдущего выпуска. Регрессия искусственно
роняет замену `previous` после `systemd-run`, подтверждает старые артефакты и
моделирует момент срабатывания: восстановленный выпуск не получает restart.
`bash ops/test-fx-factory-release.sh` и `git diff --check` прошли.

# CARD-0078 — Старый restart Пилота не прерывает новый выпуск

## HEAD

- Status: Implemented — ready for repeat review.
- Branch: `factory/754a64f9-0a5-82b4a0f4-197`.
- Specification: `knowledge/specs/pilot-restart-current-release.md`.
- Implementation commit: 1258a42e2579502f94c44b7ed1d0ff141ed385d9 — отказ
  установки janitor откатывает выпуск до назначения restart Пилота.
- What changed: обновлённый Пилот получает отложенный restart под общим
  release-lock; janitor устанавливается раньше, а его ошибка запускает rollback.
- Evidence: `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh`
  и `bash ops/test-fx-factory-release.sh` → PASS.
- Next action: Повторно проверить сценарий финальной ошибки janitor.

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

В поколенном выпуске janitor устанавливается до назначения отложенного restart
Пилота. Финальный отказ установки вызывает rollback; регрессионный сценарий
подтверждает ненулевой исход, возврат прежних бинарей и отсутствие `systemd-run`.

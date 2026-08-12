# CARD-0078 — Старый restart Пилота не прерывает новый выпуск

Implementation commit: c695193793e93b9576602882918d0e206b859361 — generation-выпуск ставит restart Пилота после metadata под общим lock.

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/99fcf773-995-eff220e2-9f2`.
- Specification: `knowledge/specs/pilot-restart-current-release.md`.
- Implementation commit: c695193793e93b9576602882918d0e206b859361 — restart
  Пилота в generation-модели защищён общим lock.
- What changed: обновлённый brain планирует restart после публикации
  `release-info`; неизменённый brain его не ставит.
- Evidence: `bash ops/test-fx-factory-release.sh` — PASS в чистом Git-клоне;
  полный набор подтвердил целевые проверки, а смежные UI и worker-сценарии
  исчерпали собственные таймауты вне области изменения.
- Next action: человек проверяет риски смежных таймаутов и вливает изменения.

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

### 2026-08-12 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Restart ставится только после публикации metadata | `bash ops/test-fx-factory-release.sh` | PASS: зафиксирован порядок `release-info ready` → `systemd-run`. |
| Старый restart не прерывает новый выпуск | shell-фикстура с занятым и свободным общим lock | PASS: при занятом lock `systemctl` не вызван, после освобождения вызван ровно раз. |
| Неизменённый brain не создаёт restart | тот же shell-сценарий | PASS: transient unit не поставлен. |
| Ошибка постановки restart откатывает metadata | сценарий `systemd-run-fail` | PASS: прежний info восстановлен или новый удалён. |
| Смежные проверки | полный локальный набор CI | `vet`, `govulncheck`, `staticcheck`, worker race — PASS; UI (8 тестов) и общий worker-набор исчерпали собственные таймауты вне diff. |

# CARD-0078 — Старый restart Пилота не прерывает новый выпуск

## HEAD

- Status: Implemented — awaiting review.
- Branch: `factory/da82a1cd-7c3-a77428a6-399`.
- Specification: `knowledge/specs/pilot-restart-current-release.md`.
- Implementation commit: d75788cb2e9e7d0027c26efbc4ed916ab929a7b5 — ранний
  rollback сохраняет прежний `release-info` при отказе установки brain.
- What changed: снимок наличия и содержимого `release-info` перенесён до
  первой rollback-capable операции; добавлен ранний failure-тест.
- Evidence: `bash ops/test-fx-factory-release.sh` → PASS; `bash -n` и
  `git diff --check` → без ошибок.
- Next action: Review проверяет общий rollback и отложенный restart Пилота.

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
`d75788cb2e9e7d0027c26efbc4ed916ab929a7b5`.

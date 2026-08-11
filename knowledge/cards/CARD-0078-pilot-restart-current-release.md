# CARD-0078 — Старый restart Пилота не прерывает новый выпуск

## HEAD

- Status: Implemented — awaiting review.
- Branch: `factory/cae0f386-943-b234212d-a0d`.
- Specification: `knowledge/specs/pilot-restart-current-release.md`.
- Implementation commit: dcb5e2c7d72f191648e8643fb18361e67d7b06b0 — отложенный
  restart Пилота перенесён после release-info и защищён общим release-lock.
- What changed: `systemd-run` запускает `/usr/bin/flock -n` на текущем
  release-lock, удерживая его до конца restart; при занятом lock устаревшая
  команда не перезапускает Пилот. Shell-регрессия покрывает порядок и оба
  состояния lock.
- Evidence: `bash ops/test-fx-factory-release.sh` → PASS; `bash -n` и
  `git diff --check` → без ошибок.
- Next action: Review проверяет изолированную правку и регрессию гонки.

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

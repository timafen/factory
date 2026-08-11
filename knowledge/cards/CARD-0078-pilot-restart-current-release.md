# CARD-0078 — Старый restart Пилота не прерывает новый выпуск

## HEAD

- Status: Implemented — awaiting review.
- Branch: `factory/fa24c4c7-759-5b254e02-e13`.
- Specification: `knowledge/specs/pilot-restart-current-release.md`.
- Implementation commit: 0157639e9daca82a9449f6281ba5293d55b20d93 — при ошибке
  постановки restart откатывается и release-info вместе с бинарниками.
- What changed: перед записью сохраняется прежний `release-info`; rollback
  восстанавливает его или удаляет новый файл, если прежнего не было.
- Evidence: `bash ops/test-fx-factory-release.sh` → PASS; `bash -n` и
  `git diff --check` → без ошибок.
- Next action: Review проверяет откат метаданных при отказе `systemd-run`.

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

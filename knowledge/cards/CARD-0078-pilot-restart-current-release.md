# CARD-0078 — Старый restart Пилота не прерывает новый выпуск

## HEAD

- Status: BLOCKED — full suite did not complete, а rebase на свежий main
  конфликтует с переработанным драйвером выпуска.
- Branch: `factory/cae0f386-943-b234212d-a0d`.
- Specification: `knowledge/specs/pilot-restart-current-release.md`.
- Implementation commit: dcb5e2c7d72f191648e8643fb18361e67d7b06b0 — отложенный
  restart Пилота перенесён после release-info и защищён общим release-lock.
- What changed: `systemd-run` запускает `/usr/bin/flock -n` на текущем
  release-lock, удерживая его до конца restart; при занятом lock устаревшая
  команда не перезапускает Пилот. Shell-регрессия покрывает порядок и оба
  состояния lock.
- Evidence: статическая проверка `bash -n` и `git diff --check` прошла; UI
  typecheck, lint и Vitest прошли. Полный Go-набор не завершился при
  одновременных оставшихся прогонах в shared runner.
- Next action: перенести lock-защиту на новый generation-драйвер из main,
  разрешить конфликт и повторить полный набор в свободном runner.

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

### 2026-08-11 — Verify

Проверена поставка от `5746dbc1fa1314497dc1fe69c68f0162e236a866` до
`66de94c989d4c64daed0d0be4d1f473c539a43e7`: release-info записывается до
постановки restart, а `/usr/bin/flock -n` получает тот же release-lock и
удерживает его до `systemctl restart`. `bash -n`, `git diff --check`, UI
typecheck, lint и Vitest прошли. Полный Go-набор не завершился: в shared runner
уже были параллельные процессы `go test`, а последовательный повтор завис на
пакетах `controlplane`/`worker`; окончательный PASS поэтому не выдан.
Свежий `origin/main` (`f90b1c74453be40a3781a8135eca5bcc6a52a112`) одновременно
переработал `ops/fx-factory-release` в generation-драйвер, поэтому обязательный
rebase даёт содержательный конфликт с этой поставкой; автоматическое разрешение
могло бы удалить новую модель выпуска.

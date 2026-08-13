# CARD-0106 — Безопасная ежедневная уборка диска Factory

Implementation commit: 714c2d868694b12f7b276e516e3f268178bfeace — реализована двухфазная уборка кэшей, карантина и старых успешных выпусков.

## HEAD

- Status: Implemented and tested
- Branch: `factory/e4c77f90-3c2-ba720dfe-780`
- Implementation commit: `714c2d868694b12f7b276e516e3f268178bfeace`
- What changed: janitor ежедневно журналирует кандидатов и удаляет только неизменившийся набор на следующем запуске; активные пути, свежие данные, неуспешные и две последние успешные версии защищены.
- Evidence: `bash ops/test-factory-janitor.sh` → 6 сценариев PASS; `bash -n ops/factory-janitor.sh ops/test-factory-janitor.sh` → PASS; `git diff --check` → PASS.
- Next action: установить и включить `factory-janitor.timer` на целевом хосте после проверки путей в service unit.

## LOG

### 2026-08-12 — Implement

Добавлены двухфазный dry-run/cleanup, fail-closed снимок активных прогонов,
защита выпусков, lock от параллельного запуска и ежедневные systemd units.
Изолированный тест подтвердил прежнее освобождение retained worktree и новые
сценарии безопасной уборки, включая отказ API.

### 2026-08-12 — Implement verification

После финальной проверки убрана лишняя пустая строка из systemd service;
целевой тест, shell syntax и `git diff --check` повторно завершились успешно.

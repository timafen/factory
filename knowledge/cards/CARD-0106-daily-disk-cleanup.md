# CARD-0106 — Безопасная ежедневная уборка диска Factory

Implementation commit: eec4fafe35dc2050e713792f71cea76a8409e58a — активные прогоны защищены путём из worker TOML, а janitor получил необходимые ограниченные права.

## HEAD

- Status: Implemented and tested
- Branch: `factory/cdf7dad9-562-a3089326-7c9`
- Implementation commit: `eec4fafe35dc2050e713792f71cea76a8409e58a`
- What changed: активная рабочая область определяется по `data_directory` из worker TOML; при неизвестном пути ежедневная очистка безопасно останавливается. Service запускает janitor с root и ограниченной записью в нужные каталоги.
- Evidence: `bash -n ops/factory-janitor.sh ops/test-factory-janitor.sh && bash ops/test-factory-janitor.sh` → 8 сценариев PASS; `git diff --check` → PASS.
- Next action: установить и включить `factory-janitor.timer` на целевом хосте после проверки оператором.

## LOG

### 2026-08-12 — Implement

Добавлены двухфазный dry-run/cleanup, fail-closed снимок активных прогонов,
защита выпусков, lock от параллельного запуска и ежедневные systemd units.
Изолированный тест подтвердил прежнее освобождение retained worktree и новые
сценарии безопасной уборки, включая отказ API.

### 2026-08-12 — Implement verification

После финальной проверки убрана лишняя пустая строка из systemd service;
целевой тест, shell syntax и `git diff --check` повторно завершились успешно.

### 2026-08-12 — Implement

Исправлена защита активных прогонов: API `/workers` используется только для
статуса занятости, а путь берётся из сопоставленного worker TOML; неизвестный
активный worker прекращает очистку до отбора кандидатов. Service теперь имеет
необходимые root-права при ограниченной записи. Целевой тест подтвердил 8 PASS.

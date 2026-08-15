# CARD-0106 — Безопасная ежедневная уборка диска Factory

Implementation commit: 5984acbd488fbc9cf91220af9564ae19ae8e3628 — активные прогоны защищены путём из worker TOML, а janitor получил необходимые ограниченные права.

## HEAD

- Status: Implemented and tested
- Branch: `factory/a550b3bd-4be-cb3cf4ab-356`
- Implementation commit: `5984acbd488fbc9cf91220af9564ae19ae8e3628`
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

### 2026-08-15 — Implement

Поставка перебазирована на свежий `main` после конфликта. Сохранены защита
retained-результатов здорового воркера и его уведомление владельцу; ежедневная
очистка по-прежнему удаляет только повторно подтверждённые безопасные кандидаты.
`bash ops/test-factory-janitor.sh` и полный `just check` завершились успешно.

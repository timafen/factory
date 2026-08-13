Implementation commit: 495aee2575614ec68c2a068168384947cde72d96 — автопоезд запускает driver без sudo, сохраняет отказ и имеет реальный cgroup fixture.

# CARD-0114 — Восстановить автопоезд и видимость отказа

## HEAD

- Status: BLOCKED — реализация и целевые проверки зелёные, но root/cgroup fixture не может выполниться в текущем worker с `NoNewPrivileges`.
- Branch: `factory/2f4f3299-a94-5deaf23b-015`.
- Implementation commit: 495aee2575614ec68c2a068168384947cde72d96 — автопоезд запускает driver без sudo, сохраняет отказ и имеет реальный cgroup fixture.
- What changed: broker запускает фиксированный driver напрямую и остаётся жив до терминальной записи; Pilot видит socket и сохраняет безопасный отказ. Изолированный transient systemd unit реально убивает broker/driver через `KillMode=control-group` и проверяет восстановленный `failed` после двух запусков.
- Evidence: releasebroker Go, 16 release-train Python, 29 Overview, installer и полный release shell fixture — PASS; Go/web build, typecheck и lint — PASS; `bash ops/test-release-broker-cgroup.sh` — SKIP без root.
- Risk: фактический PASS нового cgroup fixture ещё не получен; Review повторять нельзя.
- Next action: выполнить `CI=true bash ops/test-release-broker-cgroup.sh` в изолированной root/systemd среде и зафиксировать PASS.

## LOG

### 2026-08-13 — Implement

Broker запускает фиксированный Factory driver напрямую без `sudo`, а Pilot получает
доступ к socket через supplementary group. Durable-отказ записывается один раз,
не завершает waits и отображается без внутренних идентификаторов. Reconciliation
проверяет ровно 28 waits, не меняя live state. Обновлённый `web/dist` проходит
embedded browser gate; installer fixture подтверждает безопасный первый restart.

### 2026-08-13 — Implement

Исправлена атрибуция поставки: реализация broker и Pilot находится в коммите
`f18d6440e3c62637143eb0560bfd1d1e03e72c92`, а коммит
`172b6503e10e687c979ffe150d04c3abe1a35a51` только пересобирает встроенный
интерфейс. Fixture установки теперь корректно различает перезапуски broker и
Pilot. Целевые проверки, сборка трёх бинарников, 173 UI-теста, Overview в
реальном браузере и воспроизводимая release-сборка прошли. Production-манифест
остаётся заблокированным до ручного выпуска.

### 2026-08-13 — Implement

На ветке `factory/ab2f1b9a-cb7-8da17314-3a0` driver перестал останавливать broker в составе остановки служб и при восстановлении состояния; это сохраняет broker cgroup до записи терминального результата. Сквозной тест запускает реальный broker и driver, проверяет остановку worker, обновление службы и `succeeded`. Целевые Go и shell-проверки прошли; reconciliation остаётся заблокированной.

### 2026-08-13 — Implement

Работа заново собрана от свежего `main` без посторонних файлов. Добавлен
изолированный systemd/cgroup fixture: реальный broker запускает driver в своём
cgroup, `KillMode=control-group` убивает оба, а два перезапуска сохраняют один
терминальный `failed` без повторного driver-запуска. Все доступные целевые
проверки и сборки прошли; root-запуск fixture заблокирован `NoNewPrivileges`.

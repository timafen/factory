Implementation commit: 0166c863e6de0342934a6607ac59e2d64a86ee70 — broker не останавливается до фиксации результата, добавлена сквозная broker → driver проверка.

# CARD-0114 — Восстановить автопоезд и видимость отказа

## HEAD

- Status: PASS.
- Branch: `factory/ab2f1b9a-cb7-8da17314-3a0`.
- Implementation commit: 0166c863e6de0342934a6607ac59e2d64a86ee70 — broker не останавливается до фиксации результата, добавлена сквозная broker → driver проверка.
- What changed: release driver не останавливает родительский broker и не восстанавливает его состояние до завершения операции.
- Evidence: `go test ./internal/releasebroker ./cmd/factory-release-broker`, `bash ops/test-fx-factory-release.sh` и `bash ops/test-install-project-release-broker.sh` — PASS.
- Risk: production reconciliation намеренно остаётся заблокированной.
- Next action: выполнить полный набор проверок перед слиянием.

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

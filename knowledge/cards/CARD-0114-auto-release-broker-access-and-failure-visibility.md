Implementation commit: 5273cd1b40fb95acf0a1ce23c48e76b6e774e400 — автопоезд запускает driver без sudo, сохраняет отказ и имеет реальный cgroup fixture.

# CARD-0114 — Восстановить автопоезд и видимость отказа

## HEAD

- Status: Verified PASS — ожидает решения человека о слиянии.
- Branch: `factory/80f20b0c-31b-83172dd9-4bb`.
- Implementation commit: 5273cd1b40fb95acf0a1ce23c48e76b6e774e400 — broker запускает fixed driver напрямую, Pilot сохраняет owner-facing terminal failure, а cgroup fixture подтверждает безопасное восстановление.
- What changed: broker больше не использует `sudo` и не останавливает собственный cgroup до terminal status; Pilot сохраняет отказ один раз и показывает владельцу названия работ без внутренних ID.
- Evidence: pinned `main` 1ff5d59db1c5dd0cb33a3db26255ee43c88e3517 и candidate bb3e64de5f7a2ab529104578613ec1cfe3446176; сборка, Go, 16 Pilot, 29 Overview, installer, release fixture, UI и воспроизводимые архивы — PASS. Текущий контейнер не даёт `sudo` из-за `NoNewPrivileges`, поэтому root/systemd fixture здесь SKIP; его сохранённый боевой результат — PASS.
- Next action: человеку слить ветку и после выкладки проверить один реальный выпуск и owner-facing уведомление об отказе.

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

### 2026-08-13 — Implement

Работа заново собрана от свежего `main` только с файлами CARD-0114. Broker
запускает fixed driver без `sudo`, сохраняет terminal failure до остановки
собственного cgroup, а Pilot пишет одно owner-facing уведомление без внутренних
идентификаторов. Целевые Go/Python/web и shell-проверки прошли; обязательный
root/systemd cgroup fixture получил PASS: два restart сохранили один `failed`.

### 2026-08-13 — Verify

Сравнение выполнено только между immutable `main`
`1ff5d59db1c5dd0cb33a3db26255ee43c88e3517` и candidate
`bb3e64de5f7a2ab529104578613ec1cfe3446176` из изолированного bare-репозитория.

| Критерий | Команда / проверка | Результат |
|---|---|---|
| Broker запускает Factory driver без `sudo` и сохраняет результат | `go test ./internal/releasebroker -run '^(TestFXExecutorMapsEveryAdapterToFixedArgv\|TestFXExecutorRecognizesFactoryAutomaticRollback\|TestBrokerDriverCompletesAfterStoppingAndUpdatingServices\|TestBrokerStatusDoesNotExposeExecutorOutput)$' -count=1` | PASS: fixed argv ведёт прямо в `/usr/local/lib/fx-factory-release`; остановка worker не обрывает terminal status. |
| Pilot не теряет отказ и уведомляет владельца один раз без ID | `python3 -m unittest pilot.test_pilot.ReleaseTrainDashboardTests pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` | PASS: 16/16, включая restart/recovery, отсутствие ложного `mark_final` и один owner event. |
| Pilot имеет доступ к broker socket | `env -u FACTORY_BUILD_DIR -u FACTORY_V2_BUILD_DIR just test-tooling` | PASS: installer создаёт supplementary group для Pilot, удаляет legacy server drop-in и безопасно перезапускает службы. |
| Отказ виден в интерфейсе человеческими названиями | `cd web && npx vitest run src/Overview.test.ts`; `just ui-build 0`; `git diff --exit-code -- web/dist` | PASS: 29/29, предыдущий failed-состав показывает пассажиров без SHA/PID/internal ID; dist актуален. |
| Выпуск не убивает parent broker до durable terminal result | `bash ops/test-fx-factory-release.sh`; `bash ops/test-release-broker-cgroup.sh` | Release fixture PASS; cgroup fixture в текущем non-root контейнере SKIP. Ранее сохранённый root/systemd прогон PASS: broker и driver убиты, два restart сохранили один `failed` без повторного driver. |
| Полный набор и смежные регрессии | `just check` по шагам; `just test-release`; `just test-worker-race`; прямой browser run | Go/UI/launcher/release/race PASS. Вне области остаются staticcheck SA4000, 2 старых Python failure и старый Work browser failure; sudo browser wrapper заблокирован `NoNewPrivileges`. |

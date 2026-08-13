# CARD-0061 — Воркер не повторяет идущую команду

Implementation commit: 8cacc2554dd63dbbcfb245ea9497560b81792cc1 — Claude-службы запускаются из общего каталога для единой области flock.

## HEAD

- Status: Implemented — ready for verification.
- Branch: `factory/5dd7237e-363-723c1cf6-7d2`.
- Implementation commit: 8cacc2554dd63dbbcfb245ea9497560b81792cc1 — Claude-службы запускаются из общего каталога для единой области flock.
- What changed: общий `runCommand` сохраняет неблокирующий `flock` по argv и каноническому `cwd`.
- What changed: все systemd-службы с Claude OAuth (`factory-pilot`, `factory-intake`) имеют `WorkingDirectory=/opt/factory`.
- Evidence: `bash ops/test-claude-service-cwd.sh` → PASS, 2 службы; `go test ./internal/worker -run '^TestRunCommand' -count=1` → PASS.
- One next action: выполнить общий набор проверок перед слиянием.

## LOG

### 2026-08-12 — Implement

`factory-pilot.service` и `factory-intake.service` теперь запускаются из `/opt/factory`: их общая Claude OAuth-среда получает одинаковый `cwd`, поэтому область неблокирующего `flock` в `runCommand` совпадает. Новый `ops/test-claude-service-cwd.sh` находит каждый unit с Claude OAuth и требует этот каталог. Целевой shell-тест и `TestRunCommand*` прошли.

### 2026-08-10 — Implement

Общая граница запуска команд воркера теперь не ждёт занятый идентичный запуск, а возвращает распознаваемую ошибку. Ключ включает команду и канонический `cwd`, поэтому путь-символическая ссылка не обходит защиту. Целевые тесты подтвердили одновременный дубль, повтор после завершения, параллельные разные команды и повтор после ошибочного завершения.

### 2026-08-10 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Повтор одного полного запуска не стартует, пока первый идёт | `TestRunCommandSkipsConcurrentDuplicate` в `go test ./... -count=1` | PASS: второй вызов через символьную ссылку на тот же каталог получает `ErrCommandAlreadyRunning`. |
| После завершения команду можно повторить | `TestRunCommandAllowsRepeatAfterCompletion` | PASS: оба последовательных запуска завершаются успешно. |
| Разные команды остаются параллельными | `TestRunCommandAllowsDifferentCommandsInParallel` | PASS: обе команды достигают состояния готовности до завершения первой. |
| Ошибка процесса не оставляет блокировку | `TestRunCommandReleasesLockAfterFailure` | PASS: повтор после ошибки запускается и возвращает ошибку процесса, а не занятую блокировку. |

С чистого состояния `go test ./... -count=1` завершился успешно для 5 пакетов. `go vet ./...` и `git diff --check origin/main...HEAD` завершились успешно; implementation-коммит существует, является предком ветки и меняет код вне `knowledge/cards/`.

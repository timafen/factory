Implementation commit: 5ca87ce52a6218e0b12d13186ce4b817abe0c7b4 — выпуск перезапускает broker после установки новой версии и долговечной записи успеха

# CARD-0067 — Active release broker restarts after binary replacement

## HEAD

- Status: Shipped in PR #219; повторная постановка закрыта как `CLOSED / DUPLICATE`.
- Canonical implementation: `5ca87ce52a6218e0b12d13186ce4b817abe0c7b4` в `main` — broker detects its replaced executable and exits for systemd only after durable success.
- What changed: the release installs a distinct broker candidate; the running broker preserves the receipt, then requests service restart. Unchanged executables stay running.
- Owner boundary: `release_failed_rolled_back` не требует отдельного restart; такое расширение возможно только по новому подтверждённому сценарию расхождения процесса и восстановленного бинаря.
- Duplicate specification: `knowledge/specs/release-broker-restart-duplicate-card-0067.md`.
- Evidence: код поставки ограничивает restart статусом `succeeded`; целевые Go-тесты проверяют durable success, заменённый и неизменённый executable.
- One next action: no implementation; keep alternative CARD-0134 out of `main`.

## LOG

### 2026-08-11 — Implement

Added a second installer run with a new binary and an active-service response. The systemctl test double verifies that version 2 is already installed when `restart factory-release-broker.service` runs and rejects an `enable --now` fallback for that path.

### 2026-08-11 — Verify

| Проверка | Команда / проверка | Результат |
| --- | --- | --- |
| Активный broker перезапускается после обновления | `bash ops/test-install-project-release-broker.sh` | PASS: версия 2 уже установлена при `restart factory-release-broker.service`; повторный `enable --now` запрещён. |
| Порядок замены и перезапуска | просмотр `ops/install-project-release-broker.sh` и test double | `mv` нового бинаря выполняется до `daemon-reload` и проверки активности; активный сервис идёт в `restart`. |
| Смежные installer-пути | `just test-tooling` | PASS: сборка, обновление Go и provision-проверки вместе с обоими installer-проходами. |
| Остальной набор | `just ui-check`, `just test-launcher`, `just test-browser` | PASS: 145 UI-тестов и 19 браузерных сценариев; launcher проходит. |
| Полные Go-тесты | `just check` | Незатронутый `internal/worker.TestLostClaimAndCompletionResponsesAreIdempotent` упал: `completion=false attempts=1`; остальные завершившиеся пакеты прошли. |

### 2026-08-13 — Implement

The broker now hashes its running executable and, after a successful operation is durably committed, closes with a failure status so systemd starts the newly installed binary. Tests prove the restart follows durable success, is skipped for an unchanged binary, and that the release installs a distinct broker candidate without stopping its parent service early.

Evidence: `go test ./internal/releasebroker ./cmd/factory-release-broker` and `bash ops/test-fx-factory-release.sh` passed. The single full `just check` run passed formatting, vet, vulnerability, static, boundary, and all Go tests before finding missing local UI dependencies; after `npm ci`, `just ui-check`, `env -u FACTORY_BUILD_DIR just test-tooling test-launcher`, and `go build -o /tmp/factory-release-broker ./cmd/factory-release-broker` passed.

### 2026-08-14 — Specification

Повторная постановка закрыта как дубликат уже слитого PR #219. Решение владельца
явно исключает отдельный restart после `release_failed_rolled_back`: прежний
бинарь восстановлен, и текущий broker уже исполняет эту версию. Альтернативные
прямой `systemctl restart`, draining и CARD-0134 не переносятся; новый сценарий
для rollback потребует отдельного подтверждения.

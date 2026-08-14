Implementation commit: ad163d708e407f23261382da4a0d35e1ada588a5 — выпуск перезапускает broker после установки новой версии и долговечной записи успеха

# CARD-0067 — Active release broker restarts after binary replacement

## HEAD

- Status: Implemented and verified — awaiting human merge.
- Branch: `factory/8f06ea11-375-6280f3ad-762`.
- Implementation commit: `ad163d708e407f23261382da4a0d35e1ada588a5` — broker detects its replaced executable and exits for systemd only after durable success.
- What changed: the release installs a distinct broker candidate; the running broker preserves the receipt, then requests service restart. Unchanged executables stay running.
- Evidence: targeted Go tests and `ops/test-fx-factory-release.sh` pass; all Go checks, UI checks (180 tests), tooling, launcher, and broker build pass.
- One next action: human merge decision.

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

Implementation commit: a0bf8e400b0a78dd6b6528812995b5c00ae722d7 — тест выпуска подтверждает порядок перезапуска активного release-broker после замены программы

# CARD-0067 — Active release broker restarts after binary replacement

## HEAD

- Status: Implemented — ready for verification.
- Branch: `factory/a2ef9eb7-5e3-e406e435-e8f`.
- Implementation commit: `a0bf8e400b0a78dd6b6528812995b5c00ae722d7` — fixture закрепляет порядок обновления и перезапуска активного broker.
- What changed: второй installer-проход требует, чтобы новая программа была установлена до `daemon-reload`, проверки активности и `restart factory-release-broker.service`.
- What changed: fallback `enable --now` для уже активного broker остаётся запрещён; Pilot перезапускается после broker.
- Evidence: `bash ops/test-install-project-release-broker.sh` → PASS; `go build ./cmd/factory-release-broker` → PASS.
- One next action: выполнить независимую Verify-проверку перед слиянием.

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

Уточнена целевая fixture: второй проход теперь проверяет точную последовательность `daemon-reload` → `is-active` → restart broker → restart Pilot. Это сохраняет доказательство того, что новая программа установлена до перезапуска, и исключает fallback `enable --now` для активного сервиса.

Проверено: `bash -n ops/install-project-release-broker.sh ops/test-install-project-release-broker.sh`, `bash ops/test-install-project-release-broker.sh` и `go build ./cmd/factory-release-broker` завершились успешно.

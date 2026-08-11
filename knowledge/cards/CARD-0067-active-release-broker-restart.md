Implementation commit: 5d71cd19c9cd214ae7d5e7d3c9c17a94ab6acc5f — повторная установка проверяет замену бинаря и перезапуск активного release-broker

# CARD-0067 — Active release broker restarts after binary replacement

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/a1e4ebce-ff2-a5a6bbb7-88d`.
- Implementation commit: `5d71cd19c9cd214ae7d5e7d3c9c17a94ab6acc5f` — тест повторной установки подтверждает замену бинаря до перезапуска активного сервиса.
- Evidence summary: the target installer test passes both installation paths; static inspection and its `systemctl` double prove binary version 2 is in place before `restart`, with no repeated `enable --now`. `just ui-check`, `just test-tooling`, `just test-launcher`, and `just test-browser` pass; the full Go test command has one unrelated worker integration failure.
- One next action: human merge decision, with follow-up on the unrelated worker integration failure.

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

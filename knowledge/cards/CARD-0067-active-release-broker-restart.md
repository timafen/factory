Implementation commit: d270f5ccc3f7ecd92eb0ce079cb50299c0f03a3a — installer и unit согласованы, повторная установка перезапускает обновлённый release-broker

# CARD-0067 — Active release broker restarts after binary replacement

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/77526c28-ac9-a5079562-075`.
- Implementation commit: `d270f5ccc3f7ecd92eb0ce079cb50299c0f03a3a` — installer проверяет фактически рабочее исключение `NoNewPrivileges=false`, документированное в unit для сохранения `CAP_SETUID`.
- What changed: второй installer-проход ставит новую программу, затем требует `daemon-reload` → проверку активности → restart broker → restart Pilot.
- What changed: активный broker не уходит в fallback `enable --now`; первая установка по-прежнему включает неактивный сервис.
- Evidence: `bash ops/test-install-project-release-broker.sh`, `env -u FACTORY_BUILD_DIR just test-tooling` и сборка `factory-release-broker` — PASS на implementation commit.
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

Уточнена целевая fixture: второй проход теперь проверяет точную последовательность `daemon-reload` → `is-active` → restart broker → restart Pilot. Это сохраняет доказательство того, что новая программа установлена до перезапуска, и исключает fallback `enable --now` для активного сервиса.

Проверено: `bash -n ops/install-project-release-broker.sh ops/test-install-project-release-broker.sh`, `bash ops/test-install-project-release-broker.sh` и `go build ./cmd/factory-release-broker` завершились успешно.

### 2026-08-13 — Verify

| Проверка | Команда / проверка | Результат |
| --- | --- | --- |
| Обновлённая программа перезапускает активный broker | pinned diff и fixture `ops/test-install-project-release-broker.sh` | Второй проход требует `daemon-reload` → `is-active` → `restart factory-release-broker.service` → `restart factory-pilot.service`, а test double проверяет уже заменённую версию 2. |
| Fallback не применяется активному broker | fixture второго прохода | `enable --now factory-release-broker.service` запрещён для активного пути. |
| Полный набор | `just check` из чистого клона после `npm ci` | Базовый долг: `test-tooling` останавливается, поскольку unit в base и candidate имеет `NoNewPrivileges=false`, а неизменённый тест требует `true`; UI, Go, vet, vuln и staticcheck до этого прошли. |

### 2026-08-13 — Implement

Installer согласован с поставляемым unit без недокументированного ослабления: он требует явное `NoNewPrivileges=false`, поскольку текущий isolation profile иначе лишает root-процесс `CAP_SETUID`, нужной `setpriv` для запуска выпуска от пользователя `factory`. Fixture проверяет это значение и полный второй проход после замены программы.

Evidence на `d270f5ccc3f7ecd92eb0ce079cb50299c0f03a3a`: `bash -n ops/install-project-release-broker.sh ops/test-install-project-release-broker.sh`, `bash ops/test-install-project-release-broker.sh`, `env -u FACTORY_BUILD_DIR just test-tooling` и `go build -o /tmp/factory-release-broker-d270f5ccc3f7 ./cmd/factory-release-broker` — PASS.

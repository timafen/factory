# CARD-0134 — Выпуск перезапускает обновлённого посредника

Implementation commit: 48b044c4e401080039da3d386208e16ba0bc7000 — перезапуск привязан к фактическому production-пути посредника

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/9bcbf482-22b-eda5089d-eeb`
- Implementation commit: `48b044c4e401080039da3d386208e16ba0bc7000`
- What changed: после durable terminal commit посредник определяет замену бинарника по фактическому пути `/opt/factory-data/bin/factory-release-broker` и перезапускает systemd unit; тест сверяет этот путь с production unit.
- Evidence: pinned diff `ca4f0e35073e1e8a647c2b35ceecd42f8a9f12f5...64faf04dafb472c8a57197a462fb3e96802e32b0`; все обязательные Go/UI/tooling/launcher проверки, сборка, целевые restart-тесты и release fixture → PASS.
- One next action: человеку выполнить merge ветки в `main`.

## LOG

### 2026-08-13 — Implement

Добавлен restart после committed marker и освобождения active operation для успешного и откатившегося выпуска, который заменил broker. Неизменённый или неопределимый executable, ошибка persistence и повторный POST restart не вызывают. Целевые Go-тесты, race-проверка, release fixture, installer-тест и синтаксическая проверка прошли.

### 2026-08-13 — Implement

Исправлен блокер Review: restart теперь сравнивает запущенный процесс с бинарником по фактическому production-пути. Регрессионный тест фиксирует соответствие кода рабочему systemd unit; целевые restart/release/installer проверки, полный локальный набор и сборка прошли.

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Обновивший broker выпуск вызывает restart | `go test ./internal/releasebroker ./cmd/factory-release-broker -run 'TestBroker.*Restart\|TestBrokerPersistenceFailurePreventsRestart\|TestInstalledBrokerExecutableMatchesProductionUnit' -count=1` | PASS: restart вызван для `succeeded` и `release_failed_rolled_back`, production-путь совпадает с unit |
| Restart происходит только после durable commit и освобождения операции | те же целевые тесты, чтение `.commit` и `.json` внутри restart seam | PASS: marker `committed`, terminal record сохранён, active-operation пуста |
| Ложный или повторный restart исключён | тесты unchanged/uncertain executable, persistence failure и duplicate POST | PASS: restart не вызван |
| Release-driver не завершает broker преждевременно | `./ops/test-fx-factory-release.sh` | PASS: полный release fixture |
| Общая регрессия и сборка | `just check` с `just ui-install` для отсутствовавших зависимостей; `FACTORY_BUILD_DIR=/tmp/factory-verify-j3w63d/build just build` | PASS: Go, UI 179/179, tooling, launcher и три бинарника |

Живая служба была `active/running`, но фактический restart на worker не выполнялся: non-interactive sudo отсутствует, а `/proc/<pid>/exe` закрыт политикой доступа. Перед merge миграций и ручных шагов нет; после merge оператору желательно подтвердить смену PID на одном штатном выпуске.

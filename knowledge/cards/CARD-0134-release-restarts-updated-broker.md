# CARD-0134 — Выпуск перезапускает обновлённого посредника

Implementation commit: a7eac7c6d396b9131640ce2740f44a6c30d5304e — locked retry не запускает executor во время draining

## HEAD

- Status: Implemented — ready for verification
- Branch: `factory/4fa8a575-978-0c8c0cea-9c6`
- Implementation commit: `a7eac7c6d396b9131640ce2740f44a6c30d5304e`
- What changed: во время draining повтор существующей операции возвращает сохранённый статус, а locked retry получает 503 до запуска executor.
- Evidence: `go test ./internal/releasebroker -count=1`; целевой `-race` тест; `./ops/test-fx-factory-release.sh` → PASS.
- One next action: выполнить полную проверку перед merge.

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

### 2026-08-13 — Implement

Исправлена гонка review: при подтверждённой замене бинарника broker до освобождения mutex включает draining. Новый POST, сделанный конкурентно во время удержанного restart seam, получает 503 и не запускает операцию; idempotent POST уже завершённой операции остаётся доступным. Целевые restart-тесты и конкурентная проверка с `-race` прошли.

### 2026-08-13 — Implement

Проверка draining перенесена перед обработкой locked retry: повтор с новым SHA получает 503, сохранённая операция не меняется и executor не запускается. Конкурентный регрессионный тест, полный пакет broker, целевой `-race` и release fixture прошли.

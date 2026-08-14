# CARD-0134 — Выпуск перезапускает обновлённого посредника

Implementation commit: 604f2eac06472140b90bda01fb4eecf026e28b0e — посредник атомарно прекращает принимать новые операции перед перезапуском

## HEAD

- Status: Implemented — ready for verification
- Branch: `factory/5b44981d-5d3-a66d90ba-a9d`
- Implementation commit: `604f2eac06472140b90bda01fb4eecf026e28b0e`
- What changed: после durable terminal commit обновивший себя посредник под mutex переходит в draining до systemd restart; новые операции в этом окне получают 503.
- Evidence: `go test ./internal/releasebroker -run 'TestBroker(RestartsUpdatedExecutableAfterDurableCommit|RejectsNewOperationWhileRestartingUpdatedExecutable|DoesNotRestartUnchangedOrUncertainExecutable|PersistenceFailurePreventsRestart)' -count=1` → PASS; конкурентный тест с `-race` → PASS.
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

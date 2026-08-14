# CARD-0134 — Выпуск перезапускает обновлённого посредника

Implementation commit: 5c0324d9e120e402179a6d358056cf009cec9e75 — выпуск перезапускает обновлённого посредника после durable commit

## HEAD

- Status: Implemented — ready for Review
- Branch: `factory/f0046165-c10-ef2cdf4d-94f`
- Implementation commit: `5c0324d9e120e402179a6d358056cf009cec9e75`
- What changed: после durable commit выпуск сравнивает исполняемый файл broker с запущенным процессом и перезапускает службу при замене.
- What changed: перед restart broker переходит в draining и отвечает 503 для новых и changed locked-retry операций.
- Evidence: целевые Go-тесты с `-race` и fixture `ops/test-fx-factory-release.sh` прошли.
- One next action: выполнить Review опубликованной ветки.

## LOG

### 2026-08-13 — Implement

Пересобрана чистая поставка от `origin/main`: restart запускается только после committed terminal record и освобождения active operation, а обновлённый broker закрывает приём новой работы до замены systemd. Целевые Go-проверки с `-race` и release fixture прошли.

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

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Обновивший executable выпуск перезапускает broker после durable commit | `go test -race ./internal/releasebroker ./cmd/factory-release-broker -run 'TestBroker(RestartsUpdatedExecutableAfterDurableCommit\|PersistenceFailurePreventsRestart)\|TestInstalledBrokerExecutableMatchesProductionUnit' -count=1` | PASS: restart вызывается после committed marker и terminal record; ошибка persistence блокирует restart; production path совпадает |
| Переходный draining не принимает новую операцию | целевой `-race` тест `TestBrokerRejectsNewOperationWhileRestartingUpdatedExecutable` | PASS: конкурентный POST получает 503 до executor |
| Locked retry во время draining безопасно отклоняется | целевой `-race` тест `TestBrokerDrainingRejectsConcurrentLockedRetryWithoutLaunchingExecutor` | PASS: 503, сохранённая операция неизменна, executor не вызван |
| Необновлённый/неопределимый executable не перезапускается | целевой `-race` тест `TestBrokerDoesNotRestartUnchangedOrUncertainExecutable` | PASS: ложный restart отсутствует |
| Полный release flow и смежные проверки | `./ops/test-fx-factory-release.sh`; `just test-launcher`; `just ui-check` | PASS: fixture; launcher; UI 180/180 |
| Общая Go-регрессия и сборка | `just check` до известного baseline-сбоя installer; `FACTORY_BUILD_DIR=/tmp/factory-verify-build-qmzk4f just build` | PASS: все Go-пакеты; собраны server, worker и release-broker |

Baseline-находка вне области поставки: `ops/install-project-release-broker.sh` требует `NoNewPrivileges=true`, а неизменённый `ops/systemd/factory-release-broker.service` содержит `false`, поэтому общий `test-tooling` красный. Миграций и обязательных ручных шагов нет; фактическую смену PID под systemd на стенде эта проверка не выполняла.

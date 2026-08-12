# CARD-0089 — Проверка восстановления выпуска отдельными процессами

Implementation commit: 2414eb3a6e7802eaa3f66660d5ba7583cc2c2892 — выпуск сохраняет результат broker до завершения ожиданий и восстанавливается отдельными процессами.

## HEAD

Status: Verified PASS — ожидает слияния человеком.

Branch: `factory/7fececda-b2b-02d6d2ed-d52`.

Implementation commit: 2414eb3a6e7802eaa3f66660d5ba7583cc2c2892 — broker не меняет adapter/target при locked retry; Pilot проверяет durable crash boundaries настоящими процессами.

What changed: На чистой основе подтверждено, что тесты наблюдают состояние broker через HTTP или защищённый mutex, без гонок.

Evidence: `go test -race -count=1 ./internal/releasebroker` → PASS; `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` и обе shell fixture → PASS. Полный `just check` прошёл format/vet/vuln/staticcheck и остановился только на независимом 5-минутном timeout `internal/worker`.

Next action: Человеку принять решение о слиянии с учётом независимого timeout `internal/worker`.

## LOG

### 2026-08-11 — Implement

Свежий `origin/main` уже содержал реализацию CARD-0084, поэтому старый перенос
не применён: он затирал бы последующую работу по согласованному snapshot выпуска.
Проверены неизменяемость retry identity, реальные отдельные Pilot/broker процессы
на границах post/wrapper_status/pid/running/terminal и отсутствие гонок broker.

### 2026-08-12 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Broker сохраняет результат до terminal | `go test -race -count=1 ./internal/releasebroker` | PASS; race-проверка подтверждает durable terminal/restart recovery без повторного executor. |
| Pilot восстанавливает выпуск отдельным процессом | `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` | PASS; crash boundaries восстанавливают delivery без ложных receipt, outbox, finalization или owner completion. |
| Соседние release/install сценарии | `./ops/test-fx-factory-release.sh`; `./ops/test-install-project-release-broker.sh` | PASS; fixture проверяет последовательность выпуска и установку отдельного broker-процесса. |
| Полный регресс | `FACTORY_DATA_HOME=$(mktemp -d) just check` | format, vet, vuln, staticcheck и затронутые пакеты прошли; затем `internal/worker` упал по 5-минутному timeout SQLite/heartbeat, вне файлов реализации. |
| Чистота поставки | `git diff --check`; проверка implementation commit | PASS; whitespace-ошибок нет, implementation commit является кодовым предком ветки. |

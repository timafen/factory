# CARD-0089 — Проверка восстановления выпуска отдельными процессами

Implementation commit: 2414eb3a6e7802eaa3f66660d5ba7583cc2c2892 — выпуск сохраняет результат broker до завершения ожиданий и восстанавливается отдельными процессами.

## HEAD

Status: Verified PASS — замечания строгого review CARD-0084 уже присутствуют в свежем `main`.

Branch: `factory/7fececda-b2b-02d6d2ed-d52`.

Implementation commit: 2414eb3a6e7802eaa3f66660d5ba7583cc2c2892 — broker не меняет adapter/target при locked retry; Pilot проверяет durable crash boundaries настоящими процессами.

What changed: На чистой основе подтверждено, что тесты наблюдают состояние broker через HTTP или защищённый mutex, без гонок.

Evidence: `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests` → 7 tests OK; обе shell fixture → PASS; `go test -race ./internal/releasebroker` → PASS.

Next action: Review сверяет CARD-0084 с этой проверкой и принимает уже доставленную реализацию.

## LOG

### 2026-08-11 — Implement

Свежий `origin/main` уже содержал реализацию CARD-0084, поэтому старый перенос
не применён: он затирал бы последующую работу по согласованному snapshot выпуска.
Проверены неизменяемость retry identity, реальные отдельные Pilot/broker процессы
на границах post/wrapper_status/pid/running/terminal и отсутствие гонок broker.

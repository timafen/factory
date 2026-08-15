# Спецификация: «Задача выполнена» только после живой приёмки выпуска

## Цель и влияние на владельца

Владелец получает «Задача выполнена» только когда конкретное поколение не
только выпущено, но и принято на живой Factory. Успех release broker означает
лишь «выпущено» и не завершает Verify. Если живая проверка находит проблему,
причина сохраняется, Done не публикуется, а та же работа автоматически
возвращается в `Implement + Test`.

Это закрывает фактический дефект `pilot/pilot.py`: сейчас
`poll_delivery_state()` трактует broker `succeeded` как `completed`, после чего
`_complete_generation()` немедленно пишет receipt, вызывает
`mark_final(..., True)` и создаёт done-outbox. Поэтому успешный процесс выпуска
скрывает обнаруженный позже живой дефект, в том числе сохранённую запись
offline retained-worktree.

## Технический подход и реальные файлы

### Durable-состояние одного поколения

В существующем filesystem-backed `delivery_state_v2` в `pilot/pilot.py`
добавить фазу `released` между `running` и `completed`, не меняя SQLite.
Generation ID остаётся immutable ключом выпуска и приёмки. После broker
`succeeded` Pilot атомарно сохраняет `phase=released`, `released_at` и
`acceptance.status=pending`; `_complete_generation()` в этой фазе запрещён.

Release broker в `internal/releasebroker/broker.go` хранит рядом с неизменяемым
release request отдельный результат acceptance: `pending/running/passed/failed`,
generation ID, время и нормализованный reason code. Повторный запрос приёмки с
тем же ID возвращает durable результат; другой ID/input конфликтует. Новый
фиксированный endpoint запускает только allowlisted executable, поэтому Pilot
не получает произвольный root-command. `cmd/factory-release-broker/main.go`,
systemd unit и installer передают путь и каталог состояния.

Pilot после durable `released` запрашивает приёмку того же operation ID.
`pending/running` оставляют Verify открытым. `passed` сначала сохраняет
`phase=completed`, затем существующий recovery-safe `_complete_generation()`
создаёт по одному receipt на wait, один `generation:id:done` outbox и
`mark_final(true)`. Повторный poll/restart видит те же ключи и ничего не
дублирует.

`failed` сохраняет в generation `acceptance.status=failed`, reason code и
безопасное русское описание; delivery failure получает стабильный ID
`<generation>:live-failed`. Для каждого wait Pilot ровно один раз вызывает
существующий механизм возврата Verify с причиной на последовательные этапы
`Implement + Test`; `mark_final(true)`, delivery receipt и done-outbox не
создаются. Failure notification не называется «Задача выполнена».

### Живая приёмка и безопасный production-fixture

Добавить root-owned `ops/factory-live-acceptance`, устанавливаемый как
`/usr/local/lib/factory-live-acceptance`. Он принимает только валидные
`--generation-id` и `--commit-sha`, сверяет SHA с текущим
`factory-current.json`, проверяет health/dashboard и читает один снимок
`GET http://127.0.0.1:7337/api/v1/workers`. PASS возможен только если сервисы
отвечают, текущий выпуск совпадает и нет worker с `online=false` и непустым
`retained_worktrees`. Сохранённая запись даёт reason
`offline_retained_worktree` с человекочитаемыми именами worker/attempt, но без
секретов и произвольных путей.

Чтобы production-путь действительно покрывал этот предикат без создания,
удаления или очистки живого worktree, executable перед чтением API прогоняет
встроенный read-only fixture через тот же parser: минимальный JSON с offline
worker и retained record обязан дать ожидаемый `offline_retained_worktree`.
Несовпадение — `fixture_contract_failed` и FAIL. Затем parser применяется без
подмены к фактическому API-снимку. Fixture не пишет в control plane, не
останавливает workers и не вызывает janitor; hermetic shell-тест дополнительно
доказывает и synthetic FAIL, и фактический snapshot FAIL.

Результат executable — атомарный JSON в broker StateDirectory, привязанный к
generation ID. Неизвестный, повреждённый либо отсутствующий результат после
рестарта является pending/failed-closed, но никогда PASS. Release повторно не
запускается: `released` является отдельной durable границей.

UI, HTTP-контракт Factory, SQLite schema, чужие репозитории и ручная очистка
живых worktree вне области задачи.

## Последовательный план

1. В `pilot/pilot.py` ввести `released` и acceptance-поля; запретить completion
   на одном broker `succeeded` и добавить recovery каждой границы записи.
2. Расширить broker durable acceptance operation и фиксированный endpoint;
   обеспечить immutable ID, conflict на другой input и повторное чтение
   terminal результата без повторного release/acceptance.
3. Добавить `ops/factory-live-acceptance` с release identity, health и
   read-only worker-snapshot checks, включая обязательный self-fixture offline
   retained-worktree; установить его через существующий installer/systemd.
4. На acceptance PASS завершать generation существующим receipt/outbox
   протоколом; на FAIL записывать reason и идемпотентно возвращать каждый Verify
   wait в `Implement + Test`.
5. Добавить Python, Go и shell-регрессии рестартов, дедупликации и безопасного
   fixture; затем на Verify один раз выполнить релевантный полный `just test`.

## Критерии приёмки

| Критерий | Проверяемый результат |
| --- | --- |
| Release не равен Done | Broker `succeeded` сохраняет `released/pending`; receipt, done-outbox, `mark_final(true)` и Done notification отсутствуют. |
| Immutable identity | Release и live acceptance используют один generation ID и commit SHA; другой input получает conflict. |
| PASS ровно один раз | Live PASS после любого restart создаёт ровно один receipt на wait, один done-outbox, один final success и одну локально дедуплицированную Done notification. |
| FAIL возвращает работу | Live FAIL сохраняет reason, не создаёт успешных артефактов и ровно один раз направляет Verify в `Implement + Test`. |
| Offline retained | Production executable read-only читает workers; offline worker с retained record даёт `offline_retained_worktree` и FAIL. |
| Безопасный fixture | Self-fixture использует тот же parser, не меняет API/filesystem/systemd и fail-closes при нарушении контракта. |
| Restart | Restart после broker success, запуска acceptance, записи PASS/FAIL и до локальных side effects не повторяет физический выпуск и не дублирует side effects. |
| Границы | UI, SQLite schema, сторонние репозитории и live cleanup отсутствуют в diff. |

## Тест-план

В `pilot/test_pilot.py` расширить
`MergeReleaseDeliveryStateMachineTests`: broker success без acceptance; restart
из `released`; pending/running; PASS с crash до и после receipt/outbox/final;
FAIL с reason и crash до/после возврата; повторные polls. Каждый тест считает
broker release POST, acceptance POST/GET, receipts, `mark_final`, stage returns
и notifications.

В `internal/releasebroker/broker_test.go` проверить immutable acceptance input,
один запуск executable, disk-backed PASS/FAIL, restart из running и повторное
получение terminal результата. В новом `ops/test-factory-live-acceptance.sh`
подменить только API/current-release inputs: healthy snapshot даёт PASS;
сохранённый offline retained record даёт FAIL; fixture и live snapshot проходят
один parser; никакие mutating HTTP methods, janitor/systemctl и worktree writes
не вызываются. `ops/test-install-project-release-broker.sh` проверяет
root-owned executable и fixed broker configuration.

Целевые проверки реализации: `python3 -m unittest
pilot.test_pilot.MergeReleaseDeliveryStateMachineTests`, `go test
./internal/releasebroker`, `bash ops/test-factory-live-acceptance.sh`, `bash
ops/test-factory-janitor.sh`, `bash ops/test-fx-factory-release.sh`. Полный
`just test` запускается ровно один раз на Verify.

## Риски и решения

- Crash между release и acceptance может спровоцировать второй выпуск. Решение:
  сначала durable `released`, затем отдельная idempotent operation того же ID.
- API может быть временно недоступен. Решение: неизвестность не считается PASS;
  ограниченный retry остаётся в acceptance pending, исчерпание даёт понятный FAIL.
- Fixture может проверить не тот код, что production snapshot. Решение: fixture
  и live JSON проходят одну функцию/процесс и shell-тест фиксирует этот контракт.
- Возврат нескольких waits может задублироваться. Решение: durable map
  `returned_waits` по task ID записывается до внешнего stage handoff.
- Reason может раскрыть filesystem path. Решение: allowlist reason codes и
  словесные worker/attempt labels; сырой payload остаётся только в root journal.
- Живой retained-worktree нельзя автоматически чистить ради зелёной проверки.
  Решение: acceptance строго read-only и возвращает работу; cleanup остаётся
  отдельным существующим janitor/operator workflow.

## Карточка работы

`knowledge/cards/CARD-0174-live-acceptance-before-done.md`

## Готово, когда

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл internal/releasebroker/broker.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker_test.go
ГОТОВО-КОГДА: файл cmd/factory-release-broker/main.go
ГОТОВО-КОГДА: файл ops/factory-live-acceptance
ГОТОВО-КОГДА: файл ops/test-factory-live-acceptance.sh
ГОТОВО-КОГДА: файл ops/install-project-release-broker.sh
ГОТОВО-КОГДА: файл ops/test-install-project-release-broker.sh
ГОТОВО-КОГДА: файл ops/systemd/factory-release-broker.service
ГОТОВО-КОГДА: команда python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests

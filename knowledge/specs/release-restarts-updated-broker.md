# Перезапуск broker после обновляющего его выпуска

## Цель и влияние на владельца

Выпуск, который заменил программу `factory-release-broker`, должен сам
перезапустить активную службу broker после надёжной фиксации результата текущей
операции. Владелец больше не должен вручную исправлять процесс, который держит
удалённый inode старого бинаря: следующий выпуск проходит предflight-проверку и
работает с процессом установленной версии. Выпуск без замены broker не вызывает
лишней перезагрузки службы.

## Технический подход и реальные файлы

`ops/fx-factory-release` уже добавляет `factory-release-broker` в generation,
атомарно устанавливает артефакты и вызывает `systemctl daemon-reload`. Он также
намеренно исключает `factory-release-broker.service` из `restore_service_state`:
driver запущен в cgroup broker, поэтому остановка до завершения driver убьёт
текущий выпуск. В финале script публикует metadata/current generation и снимает
journal, но не перезапускает broker. До следующего выпуска preflight читает
`/proc/<MainPID>/exe` и отклоняет ` (deleted)`.

`internal/releasebroker/broker.go` — единственное место, где terminal-status
публикуется только после durable sequence: pending marker, запись terminal
operation и committed marker. Здесь должна появиться инъецируемая операция
перезапуска и проверка, что выполняющийся broker больше не соответствует
установленному `factory-release-broker`. Для `fx-factory-release` и только при
подтверждённой замене программа запрашивает один `systemctl restart
factory-release-broker.service` после committed marker и освобождения active
operation. Ошибка запроса restart не меняет уже подтверждённый terminal-result;
она логируется как операционная ошибка, чтобы не выдавать выпуск за
неподтверждённый. Повторный POST terminal-operation restart не запускает.

`cmd/factory-release-broker/main.go` передаст production-пути бинаря и unit в
broker; значения будут абсолютными и не будут браться из пользовательского
запроса. Для unit-тестов restart и определение замены вводятся как узкие seams,
без запуска systemd.

`internal/releasebroker/broker_test.go` проверит порядок durable commit → один
restart, отсутствие restart при неизменённой программе и rollback-путь: если
release уже заменил broker, terminal `release_failed_rolled_back` также
перезапускает службу после durable фиксации. Тест также закрепит, что сбой
durable persistence не вызывает restart.

`ops/test-fx-factory-release.sh` будет расширен systemd-fixture двумя
последовательными выпусками. Она смоделирует живой broker, замену его файла,
последующий restart и новый `MainPID`, чей `/proc/.../exe` совпадает с
установленным файлом и не оканчивается ` (deleted)`. Отдельный сценарий без
изменения broker требует ноль restart; rollback-сценарий требует тот же поздний
restart без преждевременной остановки driver.

Не менять HTTP API, формат durable operation, общую release-транзакцию,
проверку `deleted-inode` или правила перезапуска остальных служб.

## Последовательный план

1. Зафиксировать в broker зависимость для определения заменённого executable и
   безопасного единичного restart production-unit.
2. После успешного durable terminal commit вычислять необходимость restart
   только для фактического release-adapter; освободить active operation и
   отправить restart ровно один раз.
3. Передать из `main` фиксированные broker binary/unit и добавить unit-тесты
   порядка, exactly-once, неизменённого бинаря, rollback и ошибки persistence.
4. Расширить shell-fixture успешным, rollback и no-change путями; выполнить два
   последовательных выпуска в успешном сценарии.

## Критерии приёмки

- До durable terminal commit активный broker не останавливается.
- Успешный выпуск, заменивший executable broker, запрашивает ровно один restart
  строго после committed marker и terminal operation record.
- Новый `MainPID` после restart использует установленный `factory-release-broker`
  без суффикса ` (deleted)`; следующий выпуск проходит preflight.
- Два последовательных выпуска не требуют ручного restart и не получают
  `deleted-inode` от предыдущего процесса.
- Выпуск, не заменявший broker, не перезапускает его.
- Если release откатывается после уже выполненной замены broker, terminal
  `release_failed_rolled_back` durable фиксируется первым, затем служба
  перезапускается один раз; текущая операция не теряется и не запускается снова.
- Ошибка terminal persistence либо неуверенное определение замены не вызывают
  restart и не публикуют ложный terminal-result.

## Тест-план

- `go test ./internal/releasebroker -run 'TestBroker.*Restart'`: порядок
  commit/restart, exactly-once, no-change, rollback и persistence failure.
- `go test ./internal/releasebroker`: регрессия durable operation/recovery.
- `bash ops/test-fx-factory-release.sh`: интеграционная fixture двух выпусков,
  отсутствия deleted inode, rollback и отсутствия лишнего restart.
- `bash ops/test-install-project-release-broker.sh`, `bash -n
  ops/fx-factory-release`, `git diff --check`: смежная совместимость и синтаксис.

## Риски и решения

- Restart из driver преждевременно уничтожает его cgroup. Решение: не вызывать
  restart из shell-driver; инициировать его только broker после durable terminal
  boundary.
- Restart может оборвать HTTP-соединение. Клиент уже опирается на durable
  operation/status; terminal record остаётся источником истины, а повторный POST
  не исполняет выпуск повторно.
- Откат может восстановить файлы, но не старый inode уже работающего процесса.
  Поэтому поздний restart обязателен и для terminal rollback после замены.
- Неверный сигнал о замене создаст лишний restart. Решение: сравнивать только
  фиксированный installed path и фактический executable процесса, покрыв
  no-change сценарием.

## Карточка работы

`knowledge/cards/CARD-0127-release-restarts-updated-broker.md`

ГОТОВО-КОГДА: файл internal/releasebroker/broker.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker_test.go
ГОТОВО-КОГДА: файл cmd/factory-release-broker/main.go
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: команда go test ./internal/releasebroker -run 'TestBroker.*Restart'

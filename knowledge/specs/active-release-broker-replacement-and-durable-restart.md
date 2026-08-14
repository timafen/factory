# Замена active release broker и restart после durable-success

## Цель и влияние на владельца

Владелец получает предсказуемый выпуск: новый `factory-release-broker` заменяет
старый бинарь атомарно, активный `factory-release-broker.service` перезапускается
только когда текущая операция уже подтверждена durable-состоянием, а новый
процесс поднимается из установленного файла. Это устраняет окно, в котором
выпуск устанавливает новый broker, но продолжает обслуживаться старым кодом, и
не допускает ложного успеха при сбое записи результата.

## Технический подход и реальные файлы

- `ops/fx-factory-release` собирает broker в кандидатный комплект, проверяет
  active process/executable до мутации и устанавливает бинарь, unit и drop-in
  через sibling-файлы, `fsync` и `rename`; broker не останавливается до записи
  terminal-результата.
- `ops/install-project-release-broker.sh` после замены файлов делает
  `systemctl daemon-reload`; для уже active unit вызывает именно `restart
  factory-release-broker.service`, а для inactive — `enable --now`. Pilot
  перезапускается после broker.
- `cmd/factory-release-broker/main.go` передаёт broker путь собственного
  executable и callback, который закрывает HTTP-сервер с ненулевым выходом;
  `Restart=on-failure` в `ops/systemd/factory-release-broker.service` поручает
  systemd запуск установленного файла.
- `internal/releasebroker/broker.go` хеширует executable при старте и сравнивает
  его после executor. Restart разрешён только для `succeeded` после сохранения
  terminal operation и commit marker; неизменённый файл, ошибка чтения или
  любой другой статус restart не вызывают.
- `internal/releasebroker/broker_test.go` проверяет durable-success-before-
  restart, отсутствие restart без замены, сохранение результата после нового
  процесса и отказ от повторного executor; `ops/test-install-project-release-
  broker.sh` проверяет порядок установки и active/inactive ветки systemctl.

## Последовательный план

1. Зафиксировать контракт immutable operation id и путь executable, не меняя
   публичный response и не раскрывая вывод release driver.
2. Установить новый broker/unit/drop-in атомарно, выполнить `daemon-reload` и
   выбрать restart active service либо enable inactive service.
3. В broker записать `pending` marker, terminal operation и `committed` marker;
   только после успешной цепочки сравнить SHA файла и запросить выход.
4. После выхода проверить, что systemd запускает новый executable, а GET старой
   operation возвращает durable status без повторного выпуска.
5. Добавить/сохранить целевые unit, installer и Go regression tests; затем
   выполнить обязательную команду ниже.

## Критерии приёмки

1. Замена бинаря происходит до `daemon-reload` и проверки active-состояния.
2. Active broker получает `restart factory-release-broker.service`; inactive
   broker получает `enable --now`, без ошибочного enable active unit.
3. Restart callback вызывается ровно после durable `succeeded` и только если
   SHA executable изменился; failure/locked/rollback и persistence failure его
   не вызывают.
4. После restart accepted terminal status читается из StateDirectory, второй
   физический executor не запускается, а corrupt/неподтверждённая запись
   блокирует безопасный старт.
5. Сокет, права root/factory-release, systemd isolation и порядок restart Pilot
   сохраняются.

## Тест-план

- `go test ./internal/releasebroker ./cmd/factory-release-broker`: Go-контракт
  durable terminal, hash comparison и process restart.
- `bash ops/test-install-project-release-broker.sh`: изолированный installer
  fixture доказывает replacement-before-restart и active/inactive systemctl.
- `bash ops/test-fx-factory-release.sh`: release-driver fixture проверяет, что
  broker не останавливается преждевременно и комплект устанавливается целиком.
- `bash -n ops/install-project-release-broker.sh ops/fx-factory-release` и
  `git diff --check` — синтаксис и чистота документационной поставки.
- Живой systemd smoke выполнять только на разрешённом staging-хосте; локальный
  контейнер без systemd не считать доказательством production restart.

## Риски и решения

- **Crash между записью operation и marker:** commit marker и fail-closed
  recovery не публикуют неподтверждённый success.
- **Старый процесс обслуживает запрос во время install:** driver не останавливает
  broker; callback закрывает listener только после durable результата, systemd
  затем запускает заменённый файл.
- **Файл исчез или не читается:** сравнение SHA даёт no-restart, следующий
  успешный выпуск повторит безопасную проверку.
- **Повторный POST после restart:** operation id и immutable input возвращают
  сохранённый статус, а не повторяют executor.

## Карточка работы

`knowledge/cards/CARD-0128-active-release-broker-durable-restart.md`

ГОТОВО-КОГДА: файл cmd/factory-release-broker/main.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker_test.go
ГОТОВО-КОГДА: файл ops/install-project-release-broker.sh
ГОТОВО-КОГДА: файл ops/systemd/factory-release-broker.service
ГОТОВО-КОГДА: файл ops/fx-factory-release
ГОТОВО-КОГДА: файл ops/test-install-project-release-broker.sh
ГОТОВО-КОГДА: команда go test ./internal/releasebroker ./cmd/factory-release-broker && bash ops/test-install-project-release-broker.sh

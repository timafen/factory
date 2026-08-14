# Спецификация: повтор перезапуска release-broker закрывается через CARD-0067

## Цель и влияние на владельца

Не создавать вторую реализацию уже поставленного перезапуска release-broker.
После успешного выпуска владелец получает новый broker без ручного рестарта:
текущий процесс сначала долговечно сохраняет успешный результат и только затем
завершается, если установленный executable изменился; systemd запускает уже
установленную версию. Неизменённый executable оставляет процесс работающим.

Текущая постановка закрывается как `CLOSED / DUPLICATE`: это поведение уже
находится в свежем `origin/main` в поставке PR #219 и ведётся канонической
`CARD-0067-active-release-broker-restart`. Продуктовый код, UI и отдельная
CARD-0134 в этой работе не создаются.

Утверждённая граница: статус `release_failed_rolled_back` не вызывает отдельный
рестарт. После удачного rollback прежний бинарь возвращён на место, а работающий
broker уже исполняет эту же прежнюю версию. Расширить поведение можно только
новым подтверждённым сценарием, где процесс действительно расходится с
восстановленным бинарём.

## Технический подход и реальные файлы

Каноническая поставка — commit
`5ca87ce52a6218e0b12d13186ce4b817abe0c7b4` в `origin/main`:

- `cmd/factory-release-broker/main.go` получает путь текущего executable через
  `os.Executable`, включает наблюдение broker и при подтверждённой замене
  закрывает HTTP server; ненулевой выход передаёт перезапуск systemd;
- `internal/releasebroker/broker.go` сохраняет исходный SHA-256 executable,
  повторно читает файл только после committed terminal marker и вызывает
  restart callback исключительно для статуса `succeeded`;
- `internal/releasebroker/broker_test.go` проверяет заменённый и неизменённый
  executable и восстанавливает новый Broker из state directory, доказывая, что
  restart не опередил долговечную запись успеха;
- `ops/test-fx-factory-release.sh` доказывает, что штатный выпуск устанавливает
  отдельный candidate broker;
- `ops/install-project-release-broker.sh`,
  `ops/test-install-project-release-broker.sh` и systemd unit сохраняют
  возможность release-driver сменить пользователя в действующем sandbox.

Альтернативная ветка `factory/f0046165-c10-ef2cdf4d-94f` не переносится. Её
commit `5c0324d9e120e402179a6d358056cf009cec9e75` дублирует основной сценарий, но
сам вызывает `systemctl restart`, вводит draining и перезапускается также после
`release_failed_rolled_back`. Эти расширения не подтверждены владельцем.

## Последовательный план

1. Закрыть текущую постановку как дубликат поставки PR #219 и сохранить
   `CARD-0067-active-release-broker-restart` единственным источником решения.
2. Не переносить код, тесты и CARD-0134 из альтернативной ветки.
3. На последующих этапах сопоставить фактический `origin/main` с критериями:
   durable success предшествует restart, заменённый executable вызывает выход,
   неизменённый executable и rollback не вызывают restart.
4. Выполнить одну целевую Go-проверку вместе со статической проверкой ограничения
   `status == "succeeded"`.
5. Если обнаружится подтверждённое расхождение процесса с восстановленным после
   rollback бинарём, оформить отдельное предложение; не расширять этот дубликат.

## Критерии приёмки

1. После успешной операции terminal record и marker `committed` доступны новому
   Broker до запроса на перезапуск текущего процесса.
2. Если содержимое executable изменилось после запуска, успешная операция
   закрывает HTTP server и возвращает ненулевой результат, позволяя systemd
   поднять установленную версию.
3. Если executable не изменился либо его повторное чтение не удалось, broker не
   завершается из-за наблюдателя и сможет повторить сравнение после следующего
   успешного выпуска.
4. `release_failed_rolled_back`, `rollback_failed`, `failed` и `locked` не
   вызывают restart callback; отдельного поведения draining нет.
5. Текущая ветка меняет только эту спецификацию и каноническую CARD-0067;
   продуктовые файлы и альтернативная CARD-0134 отсутствуют в diff.

## Тест-план

- Выполнить обязательную команду из конца спецификации: `grep` фиксирует
  ограничение только успешным статусом, а два Go-теста проверяют порядок durable
  success и отсутствие restart для неизменённого executable.
- Статически проверить в `cmd/factory-release-broker/main.go`, что callback
  закрывает server, а запрошенный restart превращает штатное закрытие в ошибку
  процесса для политики `Restart=on-failure` systemd unit.
- Проверить `bash ops/test-fx-factory-release.sh`, если потребуется повторная
  проверка release fixture; на этапе Specification полный набор не запускается.
- Перед сдачей выполнить `git diff --check` и трёхточечный список файлов от
  свежего `origin/main`; в списке должны быть ровно два документа.

## Риски и решения

- Прямой `systemctl restart` из broker может оборвать процесс до доставки
  ответа или усложнить cgroup lifecycle. Решение: оставить канонический callback,
  закрытие server и перезапуск силами systemd.
- Draining мог бы отклонять работу даже после неудачного restart. Решение:
  не переносить неподтверждённое состояние из альтернативной реализации.
- Rollback может ошибочно восприниматься как установка новой версии. Решение:
  утверждённый контракт считает восстановленный прежний бинарь совпадающим с
  текущим процессом и не перезапускает его.
- Ошибка чтения executable может скрыть реальную замену. Решение: fail-open для
  доступности broker; следующая успешная операция повторит сравнение.
- Два источника карточек могут снова породить параллельный Implement. Решение:
  CARD-0067 остаётся канонической и фиксирует terminal duplicate для повтора;
  CARD-0134 не добавляется в `main`.

## Карточка работы

`knowledge/cards/CARD-0067-active-release-broker-restart.md`

ГОТОВО-КОГДА: файл cmd/factory-release-broker/main.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker_test.go
ГОТОВО-КОГДА: файл ops/install-project-release-broker.sh
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: файл ops/test-install-project-release-broker.sh
ГОТОВО-КОГДА: файл ops/systemd/factory-release-broker.service
ГОТОВО-КОГДА: команда sh -c "grep -Fq 'status != \"succeeded\"' internal/releasebroker/broker.go && go test ./internal/releasebroker -run '^TestBroker(RestartsOnlyAfterUpdatedExecutableAndDurableSuccess|DoesNotRestartWhenExecutableIsUnchanged)$' -count=1"

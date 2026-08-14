# Выпуск перезапускает broker после замены исполняемого файла

## Цель и влияние на владельца

Закрыть дубликат задачи: выпуск заменяет `/opt/factory-data/bin/factory-release-broker`, но уже запущенный процесс продолжает работать со старым удалённым inode. В следующем выпуске он должен гарантированно уступить место новой программе только после того, как результат текущей операции долговечно сохранён. Владельцу не нужен повторный выпуск: исправление уже находится в `origin/main` в squash-коммите `5ca87ce52a6218e0b12d13186ce4b817abe0c7b4` (#219) и было проверено целевыми сценариями.

## Технический подход и реальные файлы

Реализация уже выполнена и не меняется этой работой.

- `ops/install-project-release-broker.sh`: устанавливает новый broker через временный файл и `mv`, затем выполняет `daemon-reload`; для активного `factory-release-broker.service` вызывает `restart`, иначе `enable --now`.
- `cmd/factory-release-broker/main.go` и `internal/releasebroker/broker.go`: broker запоминает хеш собственного executable; после durable-success завершает работу с ошибочным статусом, если executable был заменён, чтобы systemd поднял новую программу. При неизменённом executable не завершает работу.
- `internal/releasebroker/broker_test.go`: проверяет завершение после durable-success при изменившемся executable и отсутствие завершения без замены.
- `ops/test-install-project-release-broker.sh`: проверяет, что новая версия установлена до `restart factory-release-broker.service` и что вместо него не применяется `enable --now`.
- `ops/test-fx-factory-release.sh`: проверяет кандидат broker в payload и отсутствие раннего `stop factory-release-broker.service` со стороны родительского выпуска.
- `knowledge/cards/CARD-0067-active-release-broker-restart.md`: фиксирует корректный полный SHA squash-коммита и закрытый статус дубликата.

## Последовательный план

1. Сохранить replacement binary атомарно до перезагрузки systemd-конфигурации.
2. Перезапустить активный сервис broker после установки; не останавливать его раньше завершения текущего выпуска.
3. В процессе broker сравнить сохранённый хеш запуска с текущим executable после durable-success.
4. При отличии завершить broker так, чтобы systemd запустил новый binary; при совпадении продолжить работу.
5. Подтвердить порядок installer и переход broker целевыми shell- и Go-тестами.
6. Для данного дубликата не повторять реализацию или релиз; поддерживать ссылку карточки на уже влитый squash-коммит.

## Критерии приёмки

- Следующий выпуск не останавливается из-за работы broker со старым удалённым inode.
- До `restart factory-release-broker.service` на диске уже находится новый исполняемый файл.
- Активный broker не останавливается досрочно родительским сценарием выпуска.
- После durable-success broker с заменённым executable завершает работу, и systemd запускает новый binary.
- Broker с неизменённым executable не перезапускается.
- CARD-0067 содержит полный SHA `5ca87ce52a6218e0b12d13186ce4b817abe0c7b4`, отмечает реализацию и проверку в `origin/main` и не требует повторного выпуска.

## Тест-план

- `bash ops/test-install-project-release-broker.sh`: атомарная установка, порядок `daemon-reload`/проверки активности/`restart`, запрет fallback `enable --now` для активного сервиса.
- `bash ops/test-fx-factory-release.sh`: payload с кандидатом broker и отсутствие ранней остановки родительского broker.
- `go test ./internal/releasebroker ./cmd/factory-release-broker`: changed executable вызывает рестарт только после durable-success; unchanged executable сохраняет процесс.

## Риски и решения

| Риск | Решение |
| --- | --- |
| Удалённый inode оставляет старый процесс до следующей операции | Хеш executable сравнивается после долговечной записи результата, затем процесс отдаётся systemd на перезапуск. |
| Ранний stop прерывает текущий выпуск | Installer перезапускает только сервис после установки нового файла; сценарий выпуска не делает ранний `stop`. |
| Рестарт без необходимости создаёт простой | Завершение выполняется только при изменении хеша executable. |
| Устаревшая ссылка в карточке создаёт ложное впечатление, что работа не влита | CARD-0067 ссылается на полный SHA squash-коммита #219 из `origin/main`. |

## Карточка работы

- Карточка: `knowledge/cards/CARD-0067-active-release-broker-restart.md`.
- Статус: закрыть как duplicate / already implemented.
- Реализация: squash-коммит #219 `5ca87ce52a6218e0b12d13186ce4b817abe0c7b4` в `origin/main`.
- Решение владельца: отдельную задачу на устаревшую ссылку не создавать; исправить CARD-0067 в рамках текущего закрытия; повторный выпуск не нужен.

ГОТОВО-КОГДА: файл ops/install-project-release-broker.sh
ГОТОВО-КОГДА: файл cmd/factory-release-broker/main.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker_test.go
ГОТОВО-КОГДА: файл ops/test-install-project-release-broker.sh
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: команда bash ops/test-install-project-release-broker.sh

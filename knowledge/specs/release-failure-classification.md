# Классификация неуспешных выпусков Factory

## Цель и влияние на владельца

У владельца должен быть правдивый, безопасный итог каждого неуспешного выпуска
Factory. Сейчас `FXExecutor` сводит почти любой ненулевой код драйвера к
`rollback_failed`: так предполётный отказ и упавший gate ошибочно выглядят как
неудачное восстановление. После реализации `rollback_failed` будет означать
только то, что безопасное восстановление не завершилось или не подтверждено.

В интерфейс и уведомления попадёт только структурный код с русским объяснением:
этап, результат восстановления и следующее действие. Вывод `fx-factory-release`
и закрытый журнал не передаются дальше даже после «очистки»: задача sanitization
и модель доступа к журналу не входят в эту работу.

## Технический подход и реальные файлы

Контракт выхода `ops/fx-factory-release` фиксируется до вызова broker:

| Код | Broker outcome | Сообщение владельцу |
| --- | --- | --- |
| 4 | `release_preflight_failed` | Предполётная проверка не пройдена; выпуск не начинался; исправьте подготовку и повторите. |
| 5 | `release_gate_failed` | Обязательная проверка кандидата не пройдена; выпуск не начинался; исправьте кандидат и повторите. |
| 6 | `release_failed_rolled_back` | Выпуск не удался; прежний комплект возвращён; проверьте кандидат перед следующим выпуском. |
| 7, 9 | `rollback_failed` | Восстановление небезопасно или не подтверждено; не выпускайте повторно, выполните указанную безопасную процедуру. |
| иной ненулевой код/ошибка запуска | `release_failed` | Выпуск не завершён; итог восстановления неизвестен; проверьте закрытый журнал по штатной процедуре. |

`internal/releasebroker/broker.go` должен отображать коды только для Factory
release-адаптеров, расширить durable/terminal whitelist и не возвращать stdout/
stderr. `internal/releasebroker/broker_test.go` закрепит всю таблицу и
устойчивость сохранённого статуса после restart.

`internal/controlplane/project_adapters.go`, его тест и `migrations/021_projects.sql`
расширят допустимые outcome и сохранят только русское статическое сообщение.
`internal/protocol/types.go`, `web/src/types.ts` и компонент операций проектов
примут новые значения и покажут это сообщение без поля с логом. Если миграция
021 уже применялась, вместо её переписывания добавить новую миграцию, расширяющую
SQLite CHECK; имя выбрать по следующему свободному номеру на implementation-ветке.

`pilot/pilot.py` и `pilot/test_pilot.py` признают все terminal failure outcome
одинаково для завершения generation, сохраняя код для безопасного notification.
`ops/fx-factory-release` получает явные константы кодов и больше не возвращает
4 после успешного rollback; `ops/test-fx-factory-release.sh` проверяет реальные
пути preflight/gate/rollback и коды 4, 5, 6, 7, 9.

## Последовательный план

1. Зафиксировать именованные коды драйвера и исправить rollback wrapper: после
   подтверждённого rollback вернуть 6, при небезопасном восстановлении — 7/9.
2. В broker добавить четыре безопасных terminal outcome, точное отображение
   кодов и backward-compatible чтение старых записей.
3. Протащить outcome через control plane, БД, protocol и web; для каждого
   сформировать только фиксированное русское объяснение и действие.
4. Научить Pilot завершать delivery по новым terminal outcome без текста лога.
5. Добавить table-driven Go, shell и Pilot/UI тесты, включая restart durable
   записи и запрет утечки runner output.

## Критерии приёмки

1. Коды 4 и 5 не создают статус `rollback_failed`; владелец видит этап и
   действие, что выпуск не начинался.
2. Код 6 означает только неуспешный выпуск с успешно подтверждённым возвратом
   прежнего комплекта; control plane дополнительно проверяет health.
3. Только коды 7/9 или неудачная внешняя проверка восстановления приводят к
   `rollback_failed`.
4. Иной ненулевой код и ошибка запуска получают `release_failed`, а не ложный
   rollback outcome.
5. Все новые статусы durable, terminal и допустимы в API/SQLite/UI/Pilot; старые
   записи остаются читаемыми.
6. В API, UI и уведомлениях отсутствуют stdout, stderr и строки release-журнала.

## Тест-план

- `go test ./internal/releasebroker ./internal/controlplane`: таблица exit-code →
  outcome, reload broker, reconciliation и статические owner messages.
- `bash ops/test-fx-factory-release.sh`: fixture для preflight, gate, успешного
  rollback и небезопасных ветвей возвращает соответственно 4/5/6/7/9.
- `python3 -m unittest pilot.test_pilot`: Pilot завершает generation для каждого
  нового terminal outcome, не сериализуя runner output.
- Целевой web-тест компонента project operation: все категории рендерят русское
  безопасное пояснение и не имеют поля лога.

## Риски и решения

- Код 6 сам по себе не доказывает живую систему: control plane сохраняет
  `release_failed_rolled_back` только после health-проверки, иначе `rollback_failed`.
- Неизвестный код не следует объявлять безопасным: отдельный `release_failed`
  сообщает неопределённость и не маскирует её rollback-статусом.
- Изменение старой миграции сломает уже развёрнутые БД: применяется новая
  add-and-copy migration для CHECK constraint.
- Даже очищенный текст может раскрыть секрет: продукт передаёт только заранее
  заданные строки; доступ к закрытому логу остаётся вне UI и уведомлений.

## Карточка работы

`knowledge/cards/CARD-0125-release-failure-classification.md`

ГОТОВО-КОГДА: файл ops/fx-factory-release
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: файл internal/releasebroker/broker.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker_test.go
ГОТОВО-КОГДА: файл internal/controlplane/project_adapters.go
ГОТОВО-КОГДА: файл internal/controlplane/project_adapters_test.go
ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл migrations/022_release_failure_statuses.sql
ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл web/src/types.ts
ГОТОВО-КОГДА: файл web/src/Projects.tsx
ГОТОВО-КОГДА: файл web/src/Projects.test.tsx
ГОТОВО-КОГДА: команда go test ./internal/releasebroker ./internal/controlplane

# Спецификация: штатный выпуск не превращает остановленные этапы в неудачные работы

## Цель и влияние на владельца

Штатный выпуск Factory должен либо дождаться уже выполняемых этапов, либо
безопасно отложиться. Он не должен принять новый этап после последней проверки
`active_count`, остановить его вместе с воркером и показать владельцу ложную
продуктовую неудачу.

После реализации история работы будет различать настоящий `failed` (ошибка
этапа) и техническую паузу на время выпуска: этап, не начатый из-за закрытого
приёма, останется в очереди и продолжится после запуска обновлённого воркера.
Обычная отмена владельцем, таймаут и реальная ошибка не меняют своей семантики.

## Технический подход и реальные файлы

Сейчас `ops/fx-factory-release` останавливает Pilot и Intake, затем опрашивает
`GET /api/v1/workers` до нулевого `active_count` и останавливает воркеры.
Однако `internal/worker/manager.go` самостоятельно вызывает
`reserveAndClaim`, а `internal/controlplane/state.go:Claim` продолжает
создавать попытки для любого здорового воркера. Поэтому остановка Pilot не
является барьером admission.

Реализация добавит сохраняемый control-plane флаг **release admission closed**
и служебные защищённые операции закрытия/открытия. Закрытие и проверка права
на claim выполняются в одной транзакционной модели `Store`: после успешного
закрытия новый claim возвращает обычный пустой ответ `204`, не создавая
`attempt`, не увеличивая `active_count` и не меняя `execution` из `queued`.
Идемпотентный повтор уже выданного claim остаётся доступным только для его
исходной попытки; новый claim не получает работу.

`ops/fx-factory-release` сначала закрывает admission через локальный
аутентифицированный control-plane интерфейс, затем останавливает Pilot/Intake
и ждёт drain. При timeout, сбое закрытия либо иной ошибке до остановки воркеров
скрипт открывает admission и возвращает текущий retryable-код без изменения
этапов. После установки, запуска сервера и воркеров он открывает admission
только после успешной проверки runtime; rollback восстанавливает предыдущее
согласованное состояние. Никакой остановленный выпуском активный этап не
переклассифицируется в `failed`: fence не допускает такой попытки к остановке.

Файлы реализации:

- `internal/protocol/types.go` — контракт служебного состояния admission и
  ответов API;
- `internal/controlplane/state.go` — хранение флага, атомарная проверка в
  `Claim`, идемпотентность и открытие/закрытие;
- `internal/controlplane/http.go` — локальные аутентифицированные маршруты
  release-admission и запрет внешнего неавторизованного переключения;
- `internal/controlplane/store_test.go` — транзакционные сценарии claim,
  закрытия и повторного открытия;
- `internal/controlplane/http_test.go` — контракт API и проверка полномочий;
- `internal/worker/manager.go` и `internal/worker/claiming.go` — обработка
  пустого claim при fence без unhealthy-состояния или terminal completion;
- `internal/worker/worker_integration_test.go` — гонка «fence → claim → stop»;
- `ops/fx-factory-release` — порядок close/drain/stop/open и rollback;
- `ops/test-fx-factory-release.sh` — герметичная release-fixture этой гонки.

UI, ручное «Оживить», продуктовые retry-политики и семантика настоящих ошибок
не входят в область.

## Последовательный план

1. Определить в protocol и Store одно durable-состояние admission, доступное
   только локальному release-процессу; добавить миграцию, если текущая схема не
   содержит подходящего системного singleton.
2. Внести проверку fence в `Store.Claim` до выбора queued execution и создания
   attempt, сохранив безопасное воспроизведение уже выданного request ID.
3. Добавить локальный защищённый API закрытия, чтения и открытия, с
   идемпотентными переходами и явной ошибкой, если состояние нельзя сохранить.
4. Изменить release-скрипт: close admission перед остановкой orchestrators,
   дождаться нуля, затем остановить воркеры; открыть admission после здорового
   запуска или при любой отсрочке/rollback до остановки воркеров.
5. Добавить детерминированные тестовые барьеры: закрыть admission сразу после
   нулевого чтения, попытаться claim и подтвердить, что worker stop не видит
   новую попытку и история не содержит ложного `failed`.
6. Запустить целевые Go- и shell-проверки, затем зафиксировать фактический
   способ миграции и результаты в карточке реализации.

## Критерии приёмки

- После подтверждённого закрытия admission никакой новый request ID не создаёт
  attempt, не переводит execution из `queued` и не повышает `active_count`.
- Воспроизводимая гонка «`active_count == 0` → worker sends claim → release
  stops workers» оставляет этап queued; после открытия он исполняется без
  нового продуктового круга и без `failed` в истории.
- Повтор того же уже принятого request ID не нарушает lease-идемпотентность,
  а обычные healthy/offline/capacity-ограничения сохраняются.
- Timeout drain возвращает retryable-результат, запускает ранее активные
  orchestration services и открывает admission; `stop factory-worker` не
  вызывается.
- Ошибка закрытия, установки, runtime-проверки или rollback не оставляет
  систему навсегда закрытой; открытие происходит только когда сервер способен
  принять этот запрос.
- Операторская отмена, task timeout, lease loss и реальная ошибка команды
  остаются `cancelled`/`failed` по существующим правилам и не получают
  автоматического retry по признаку release.

## Тест-план

- `go test ./internal/controlplane -run 'Test.*Release.*Admission|Test.*Claim.*Admission'`
  — закрытие durable fence, API-права, пустой claim и отсутствие мутаций.
- `go test ./internal/worker -run 'Test.*Release.*Admission|Test.*Claim.*Fence'`
  — worker не считает `204` ошибкой и не завершает невыданную попытку.
- `go test ./internal/worker -run 'TestReleaseAdmissionFencePreventsClaimStopRace'`
  — обязательная детерминированная проверка сути дефекта: claim между нулевым
  drain и stop не становится `failed`.
- `bash ops/test-fx-factory-release.sh` — fixture закрывает admission до
  последнего drain, проверяет порядок событий, defer при timeout и отсутствие
  остановки занятого/только что claimed воркера.
- После реализации: `just test-worker-race` и `git diff --check` для смежной
  конкурентной регрессии и качества поставки.

## Риски и решения

- Fencing только остановкой Pilot остаётся неполным, потому что воркер имеет
  прямой claim API. Решение: authoritative проверка находится в Store, а не в
  timing/опросе shell-скрипта.
- Persistent флаг может застрять после аварии. Решение: release journal
  фиксирует фазу и recovery/rollback открывает admission после подтверждённого
  healthy server; до подтверждения безопаснее не принимать новые этапы.
- Закрытие может пересечься с уже начатым HTTP claim. Решение: fence и выбор
  execution сериализуются одной БД-транзакцией; release ждёт transactionally
  видимый ноль активных попыток только после close.
- Новый privileged маршрут может расширить поверхность атаки. Решение: принять
  только loopback/выделенную credential release-broker, покрыть 401/403-тестом
  и не публиковать переключатель в UI.
- Автоматический retry любой `cancelled` замаскирует настоящую отмену. Решение:
  не добавлять retry для terminal attempt; предотвращать выдачу этапа fence-ом.

## Карточка работы

Карточка: `knowledge/cards/CARD-0175-release-drain-admission.md`.

Статус: Specification ready. Реализация потребует отдельного code commit до
обновления поля `Implementation commit` в карточке; эта документальная стадия
не создаёт и не имитирует продуктовый commit.

ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл internal/controlplane/http.go
ГОТОВО-КОГДА: файл internal/controlplane/store_test.go
ГОТОВО-КОГДА: файл internal/controlplane/http_test.go
ГОТОВО-КОГДА: файл internal/worker/manager.go
ГОТОВО-КОГДА: файл internal/worker/claiming.go
ГОТОВО-КОГДА: файл internal/worker/worker_integration_test.go
ГОТОВО-КОГДА: файл ops/fx-factory-release
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: команда go test ./internal/worker -run 'TestReleaseAdmissionFencePreventsClaimStopRace'

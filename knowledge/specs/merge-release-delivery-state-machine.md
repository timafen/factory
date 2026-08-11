# Спецификация: единая машина состояний слияния и выпуска

## Цель и влияние на владельца

«Задача выполнена» означает не Verify PASS и не успешный `gh_merge`, а
принятый выпуск конкретного поколения и живую приёмку, которую выполняет
release driver. Пока выпуск не завершён, владелец видит честное состояние
«влито, выпуск N ожидается/идёт/не прошёл», а не ложное завершение. После
успеха он получает один результат с тем же generation id; после неуспеха —
понятный failed delivery без дублирования реального выпуска.

Цель — заменить неоднозначные `queued`, `launch_token`, `pid` и
`successor_queued` одной durable машиной. Она переживает restart после каждой
границы записи или внешнего действия, не даёт `processed` скрыть recovery
merge-intent и отличает уже зарезервированный выпуск N от запроса N+1.

## Технический подход и реальные файлы

### Граница и модель данных

Изменение ограничено Pilot, существующим root-owned release broker и
Factory release driver. Ни HTTP/UI control plane, ни schema SQLite, ни чужой
репозиторий не меняются.

В `pilot/pilot.py` заменить `post_merge_deploys` на версионированный блок
`delivery_state_v2` (запись уже атомарна через `save()` → `os.replace`). Ключ
target — разрешённая пара `repository identity + fixed release adapter`.
Текущий объект target содержит ровно один `current_generation`,
монотонный `last_generation` и отдельный boolean `next_requested`.

Каждое поколение имеет неизменяемый `id` вида
`<target>-<sequence>-<uuid>`, immutable adapter/input после начала launch,
список merge receipts и delivery waits, а также **только** одну фазу:

| Фаза | Смысл и допустимый следующий переход |
| --- | --- |
| `reserved` | Поколение записано, но реальный выпуск ещё не принят broker; повтор lock `rc=8` остаётся здесь. → `launching` или `failed`. |
| `launching` | Тот же `generation.id` отправлен idempotent broker; PID не является источником истины. → `running`, `completed` или `failed`. |
| `running` | Broker/status подтвердил активный wrapper. → `completed` или `failed`. |
| `completed` | Broker и release status подтвердили accepted release. Терминальная фаза. |
| `failed` | Broker/status подтвердили неуспех либо неустранимо неизвестный legacy outcome. Терминальная фаза. |

`delivery_waits[verify_task_id]` хранит `generation_id`, merge receipt и
статус ожидания. Только переход именно этой generation в `completed` создаёт
delivery receipt, вызывает `mark_final(..., true)` и кладёт сообщение в
outbox. `recent_done_block()` читает delivery receipts, а не один merge
journal. `failed` не делает работу готовой.

### Слияние, N и N+1

Перед внешним `gh_merge` Pilot сохраняет immutable `merge_intent` с Verify
task, branch, repository, base и target. После возврата из `gh_merge` он
сначала пишет merge receipt/journal, затем в одной durable записи создаёт или
присоединяет delivery wait. Старт `cycle()` восстанавливает intents **до**
фильтра `state["processed"]`: если ветка уже в `main`, он дописывает
пропущенный receipt и продолжает delivery; если нет — повторяет только
безопасную проверку/merge согласно intent. `processed` остаётся лишь cursor
обработки UI-задач и не является доказательством слияния или доставки.

Если текущий target в `reserved`, новый merge добавляет receipt и wait к тому
же N, обновляет только ещё не зафиксированный source snapshot и **не** ставит
`next_requested`. Это покрывает `rc=8` → новый merge → успешный один N. Если
N уже `launching` или `running`, новый merge не меняет immutable input N, а
долговечно ставит только `next_requested=true`; N+1 создаётся единожды после
терминального N. Новые merge никогда не переиспользуют или не создают
`successor_queued`.

### Честная атомарность запуска

`internal/releasebroker/broker.go` и
`cmd/factory-release-broker/main.go` становятся durable broker, а не
in-memory map. POST/GET существующего Unix API остаётся совместимым, но
operation id равен `generation.id`, а adapter, commit SHA и target —
неизменяемый запрос. До первого внешнего запуска broker атомарно сохраняет
operation/status. Повтор POST с тем же id и теми же input возвращает текущий
status; с другими input возвращает conflict. Сырой `fx` при retry Pilot не
вызывает.

Broker запускает generation-specific wrapper под его lock/status. Wrapper
сначала атомарно записывает свой `launching` status (включая generation id),
и лишь затем broker сохраняет PID; terminal status записывается самим
wrapper/driver до ответа наблюдателю. При restart broker восстанавливает
operation по durable status и lock, а не по `launch_token` или одному PID.
Неопределённый process без авторитетного status не перезапускается: он
останавливается как `failed` и требует новый generation, что предпочтительнее
второго физического выката.

`ops/systemd/factory-release-broker.service` получает durable
`StateDirectory` и правила, позволяющие дочернему wrapper пережить restart
наблюдателя; `ops/install-project-release-broker.sh` ставит эту версию.
`ops/fx-factory-release` принимает унаследованный `FACTORY_DELIVERY_ID`, под
тем же release lock создаёт/читает status конкретной операции и возвращает
уже известный terminal result без второго release. Его status является
authoritative proof для Factory release. Поддерживаемые adapter обязаны
принять тот же generation key/status contract; adapter без такого контракта
не может автоматически подтвердить `completed` и fail-closed, не завершая
работу владельца.

### Lock retry, outbox и совместимость

`rc=8` означает внешний lock, а не failed delivery: broker/Pilot сохраняет
N как `reserved` с `next_retry_at`; retry шлёт тот же generation id. Новый
merge в этот промежуток присоединяется к N. После принятых `completed` status
и live acceptance Pilot в той же durable записи создаёт outbox item с
id=`generation.id:done`. Отдельный dispatcher добавляет дедуплицированную
запись в `notifications.jsonl` и отправляет push; при crash outbox
переигрывается. Внешний push допускает at-least-once, но журнал/UI
дедуплицируются по outbox id; готовность работы от доставки push не зависит.

На первом старте V2 мигратор распознаёт старый `post_merge_deploys`, сохраняет
его raw snapshot в audit-разделе и создаёт только консервативную запись V2.
Читаемый terminal status превращается в terminal history без привязки к
новой Verify работе; живой/неизвестный legacy PID не усыновляется и не
запускается повторно. Никакой legacy записью нельзя создать новый «done».
Новые intents/waits используют V2; после одного релизного окна старые ключи
удаляются. Это сохраняет диагностику и исключает второе исполнение старой
команды вместо видимости совместимости.

Реализация не переносит код CARD-0077. Его review findings — crash после
`gh_merge`, recovery до `processed` и неоднозначность reservation/successor —
служат доказательством, почему требуется замена модели.

## Последовательный план

1. В `pilot/pilot.py` ввести V2 structures, валидатор переходов, мигратор и
   recovery intents до основного terminal-task loop; удалить чтение/запись
   рабочих флагов `queued`, `launch_token`, `pid`, `successor_queued`.
2. Перенести `gh_merge` в intent → external merge → receipt/wait protocol;
   отложить `mark_final(true)`, owner done и dashboard completion до
   generation `completed`.
3. Реализовать правила присоединения merge к `reserved` N, `next_requested`
   только для N+1 и retry `rc=8` без смены id N.
4. Сделать broker persistent: immutable operation request, state/status на
   диске, idempotent POST/GET, wrapper-status-before-PID и recovery без raw
   re-execution. Передать operation id в фиксированный FX executor.
5. Добавить generation status/idempotency в `ops/fx-factory-release` и
   установить durable state directory через systemd/installer.
6. Добавить outbox/receipt dispatcher и обновить `recent_done_block`; покрыть
   migration, каждую crash boundary и один настоящий Factory release fixture.
7. Запустить целевые Python, Go и shell тесты, затем полный `just check`;
   проверить, что diff не затрагивает UI/control-plane и что новая модель не
   принимает legacy флаги как активное состояние.

## Критерии приёмки

| Критерий | Проверяемый результат |
| --- | --- |
| Единственная модель | В durable V2 generation имеет id и только `reserved/launching/running/completed/failed`; старых active flags нет. |
| Правильная готовность | Verify PASS и merge не публикуют `Задача выполнена`; receipt, `mark_final(true)` и done-outbox возникают только после accepted release + live acceptance. |
| Recovery merge | Crash после intent, после `gh_merge` до journal и после journal до wait восстанавливает один receipt/wait до проверки `processed`; второго merge нет. |
| N против N+1 | При `rc=8` новый merge joins `reserved` N, N retry succeeds once; merge во время launching/running создаёт ровно один N+1. |
| Launch safety | Crash до/после launch, после wrapper status и до PID persistence повторяет только POST того же id; physical release выполняется не более одного раза. |
| Terminal recovery | Restart во всех фазах возвращает status/lock и заканчивает/честно fail-closes wait без потерянного delivery и без повторного external release. |
| Outbox | Restart до/после journal и отправки notification не создаёт второй local done record; owner completion не зависит от push transport. |
| Legacy | Старый state читается для audit, не становится новым done и не вызывает повтор старой команды; новая работа сразу использует V2. |
| Изоляция | Diff меняет только перечисленные Pilot/broker/release-driver тестовые файлы; UI, migrations и control-plane не меняются. |

## Тест-план

В `pilot/test_pilot.py` добавить table-driven full-cycle fixtures с настоящим
state file и restart после каждой точки: (1) сохранён intent, (2) возврат
`gh_merge` до journal, (3) journal до wait, (4) `reserved` до broker POST,
(5) POST до wrapper status, (6) wrapper status до PID persistence, (7)
`running` до terminal status, (8) terminal status до receipt/outbox, (9)
outbox до/после notify. Каждый сценарий считает `gh_merge`, broker POST,
physical release и owner done.

Отдельный сценарий: N получает `rc=8`, между retry приходит второй merge,
оба waits привязаны к N, один broker operation реально succeeds и не
появляется N+1. Парный сценарий для merge после `launching` доказывает ровно
один N+1. Проверить `processed` с уже завершённой Verify задачей и
необработанным merge-intent.

В `internal/releasebroker/broker_test.go` проверить immutable conflict,
duplicate POST на disk-backed broker, restart broker во время wrapper,
status-before-PID и один `FXExecutor.Execute`. В
`ops/test-fx-factory-release.sh` выполнить один реальный fixture release с
одним `FACTORY_DELIVERY_ID`, затем повторить тот же id и доказать отсутствие
второй установки; crash fixture читает тот же terminal status. В
`ops/test-install-project-release-broker.sh` проверить StateDirectory и
безопасный upgrade running broker.

Обязательная новая проверка:
`python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests`.
Полный регрессионный набор перед передачей: `go test ./internal/releasebroker`,
`bash ops/test-fx-factory-release.sh`,
`bash ops/test-install-project-release-broker.sh` и `just check`.

## Риски и решения

- Транзакции между filesystem, GitHub, broker и push не бывают атомарными.
  Решение: intent/receipt/outbox сохраняются до внешнего шага, запросы имеют
  immutable generation id, а status/lock — авторитетная граница повторов; при
  неизвестном исходе fail-closed, а не «надеемся, что второй запуск безопасен».
- `rc=8` не является неуспехом выпуска. Решение: N остаётся `reserved`, а
  retry не выделяет generation и не превращает merge в N+1.
- Прежний in-memory broker теряет operation map при restart. Решение:
  StateDirectory, persistent status и wrapper lock; PID — лишь диагностика.
- Legacy `pid`/`launch_token` нельзя надёжно связать с Verify task. Решение:
  audit-only migration и запрет legacy done, а не опасное усыновление.
- Не все внешние adapters могут подтвердить idempotency key. Решение:
  автоматическая готовность разрешена только adapter со status contract;
  остальные останавливаются честно до owner done. Это явное ограничение,
  а не ложное обещание exactly-once.
- Diff может разрастись до переписывания pipeline/UI. Решение: не менять
  control-plane/UI/SQLite; новые функции локальны в Pilot, broker и release
  driver, а acceptance проверяет точный список файлов.

## Карточка работы

`knowledge/cards/CARD-0084-merge-release-delivery-state-machine.md`

## Готово, когда

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл internal/releasebroker/broker.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker_test.go
ГОТОВО-КОГДА: файл cmd/factory-release-broker/main.go
ГОТОВО-КОГДА: файл ops/systemd/factory-release-broker.service
ГОТОВО-КОГДА: файл ops/install-project-release-broker.sh
ГОТОВО-КОГДА: файл ops/test-install-project-release-broker.sh
ГОТОВО-КОГДА: файл ops/fx-factory-release
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: команда python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests


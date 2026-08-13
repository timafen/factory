# Обзор показывает поезд выпуска: что едет и когда следующий

## Цель и влияние на владельца

Владелец видит на «Обзоре» один честный блок «Поезд выпуска»: что сейчас
зарезервировано или выпускается, на каком оно шаге, какие работы уже едут,
что ждёт следующий состав и чем/когда закончился предыдущий. Это снимает
необходимость сопоставлять «Сделано недавно», задачи и логи broker вручную.

Блок не обещает расписание, которого система не знает. В частности,
`reserved` означает, что поколение ещё не принято broker (в том числе при
retry после lock), а `next_requested` означает только наличие следующего
состава после терминального текущего поколения, не его время старта.

Вне scope: правила merge/release, очередь broker, durable state,
SQLite-схема, интервалы retry и поведение release adapter.

## Технический подход и реальные файлы

Единственный источник API — атомарный `pilot/dashboard.json`: `pilot/pilot.py`
уже строит его в `dashboard()` из `delivery_state_v2`; обработчик
`internal/controlplane/dashboard_http.go` только отдаёт этот файл, поэтому
не выполняет новых запросов к broker и не собирает состояние на чтении.

В `dashboard()` добавить top-level контракт `release_train`. Он строится
только из `delivery_state_v2.targets`, а последняя доставка — только из
durable generation/receipt, никогда из уведомлений. Если state отсутствует,
невалиден, target не распознан или в нём нет проверяемой current/history,
`release_train` отсутствует (либо равен `null`); это равнозначно честному
unavailable, а не «свободно».

Контракт снимка (без внутренних id, SHA, socket/PID и command):

```ts
type ReleaseTrainSnapshot = {
  updated_at: string;
  trains: Array<{
    target: string;                 // стабильное человекочитаемое имя назначения
    state: "idle" | "waiting" | "running" | "succeeded" | "failed";
    generation?: number;            // sequence, не внутренний generation id
    gate?: "ожидает broker" | "запускается" | "выполняется" | "принят" | "не прошёл";
    started_at?: string;            // только когда момент известен durable state
    elapsed_seconds?: number;       // только для reserved/launching/running
    passengers: Array<{ title: string }>;
    next: { requested: boolean; passengers: Array<{ title: string }>; retry_at?: string };
    previous?: { state: "succeeded" | "failed"; finished_at?: string; passengers: Array<{ title: string }> };
  }>;
};
```

`passengers` берутся из waits текущей generation, сопоставляя `task_id` с
названием pipeline-работы; неизвестный/удалённый task показывается как
«Работа из выпуска (название недоступно)», не скрывается и не получает
выдуманное название. Для `next.passengers` используются только
`next_waits`; при `reserved` новые merge уже входят в текущий состав, потому
`next.requested=false`. Для `launching`/`running` значение
`next_requested=true` и `next_waits` описывают ближайший будущий состав.

Время: `next.retry_at` сериализуется исключительно из числового
`next_retry_at` текущего `reserved` в UTC RFC3339. Его отсутствие означает
«время следующей попытки неизвестно». При `next_requested` без retry_at UI
пишет «сядет в ближайший выпуск после текущего», без даты. `elapsed_seconds`
вычисляется от durable `started_at`/`reserved_at`; если старое поколение не
имеет timestamp, поле опускается и UI показывает «длительность неизвестна».
Реализация должна записывать эти timestamps только для новых переходов, не
меняя transition semantics. Projection-тест обязан передавать в builder явный
фиксированный `now`; он не должен зависеть от часов машины и не должен вызывать
`pilot.time.time()`. Для этого тест временно заменяет `pilot.time.time` на
ошибку, вызывает builder с `now=120` и проверяет одновременно фиксированный
`updated_at` и `elapsed_seconds` относительно durable `reserved_at`/`started_at`.

`web/src/Overview.tsx` расширяет тип `Dash` и добавляет единый section с
aria-label «Поезд выпуска» после верхнего статуса и до «Сейчас в работе».
Он рендерит одну компактную карточку на target внутри section, сортируя
стабильно по target. `idle` — «свободен»; `waiting` — «ожидает выпуска»;
`running` — «выполняется»; terminal состояния показывают результат прошлого
состава и, если появился новый, его отдельное состояние. При неточном или
пустом API section всё равно виден с текстом «Сведения о выпуске недоступны».
Клиент не выводит generation id, SHA и не вычисляет расписание сам.

Тестовые точки: `pilot/test_pilot.py` проверяет exact JSON projection на
снимках V2; `web/src/Overview.test.ts` проверяет русские состояния и
отсутствие ложного времени. `internal/controlplane/dashboard_http_test.go`
дополняется только если в нём уже есть проверка JSON-файла: endpoint обязан
передать `release_train` без преобразования.

## Последовательный план

1. Выделить в `pilot/pilot.py` чистый builder `release_train_block(state, tasks, now)` и добавить timestamps к новым generation transitions без изменения broker-вызовов.
2. Сопоставить waits текущего и следующего состава с pipeline title, свести фазы V2 к пяти публичным состояниям и выбрать последнюю terminal generation как `previous`.
3. Включить готовый блок в `dashboard()`; malformed/legacy state сделать unavailable.
4. Расширить `Dash`, formatter времени и section «Поезд выпуска» в `web/src/Overview.tsx`.
5. Добавить пилотные contract-тесты и UI-тесты всех состояний; при существующем HTTP-тесте подтвердить прозрачную сериализацию endpoint.
6. Выполнить целевые тесты, typecheck и lint; не менять release broker, adapters либо storage schema.

## Критерии приёмки

| Сценарий | Наблюдаемый результат |
| --- | --- |
| Нет достоверного снимка | На Обзоре есть «Поезд выпуска» и «Сведения о выпуске недоступны». |
| Нет current generation | Карточка сообщает «свободен», только когда V2 target достоверно существует и активного выпуска нет. |
| `reserved` | «ожидает выпуска», номер поколения, пассажиры; дата retry показана лишь при `next_retry_at`. |
| `launching`/`running` | «выполняется», gate, известная длительность и пассажиры текущего выпуска. |
| `completed`/`failed` | Видны прошлый результат и время, если durable timestamp есть; успешный результат не смешан с failed. |
| N против N+1 | merge в `reserved` остаётся пассажиром N; при `next_requested` видны пассажиры N+1 и формулировка «после текущего». |
| API | Snapshot стабилен, не раскрывает SHA/PID/internal generation id и не запускает новые вызовы broker. |

## Тест-план

- `pilot/test_pilot.py`: table-driven `release_train_block` для unavailable, idle, reserved с/без retry, launching, running, completed, failed и `next_requested`; проверка task-title fallback, elapsed и публичного JSON без секретных/внутренних полей.
- `pilot/test_pilot.py::ReleaseTrainDashboardTests.test_projection_uses_explicit_now_without_machine_clock`: замокать `pilot.time.time` исключением, вызвать projection с фиксированным `now` и подтвердить, что `updated_at` и `elapsed_seconds` вычислены только из него и durable timestamp.
- `web/src/Overview.test.ts`: mock `/api/v1/dashboard`; проверить доступный section, состояния свободен/ожидает/выполняется/успешно/ошибка, gate, длительность, пассажиров и N+1; отдельный test доказывает отсутствие даты при неизвестном retry.
- `internal/controlplane/dashboard_http_test.go` (если fixture покрывает handler): записать dashboard JSON и проверить точный passthrough `release_train`.
- Целевой запуск: `python3 -m unittest pilot.test_pilot.ReleaseTrainDashboardTests.test_projection_uses_explicit_now_without_machine_clock`, затем `python3 -m unittest pilot.test_pilot.ReleaseTrainDashboardTests`, `npm --prefix web test -- --run src/Overview.test.ts`, `npm --prefix web run typecheck` и `npm --prefix web run lint`.

## Риски и решения

- У старых generations может не быть начала/окончания. Решение: опускать время и явно показывать неизвестность; не выводить расчёт из номера или времени HTTP-ответа.
- Данные task API могут исчезнуть. Решение: сохранять число/позицию и безопасный fallback, а не скрывать пассажира.
- `next_requested` легко принять за календарное расписание. Решение: это булевый факт очереди; дата разрешена только из `next_retry_at`.
- Несколько targets не должны превращаться в несколько несогласованных виджетов. Решение: один section, стабильные target-cards и единый snapshot одного файла.
- Проекция может нечаянно изменить delivery state. Решение: builder read-only, существующие `poll_delivery_state` и broker tests остаются без логических изменений.

## Карточка работы

`knowledge/cards/CARD-0103-overview-release-train.md`

## Готово, когда

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл web/src/Overview.tsx
ГОТОВО-КОГДА: файл web/src/Overview.test.ts
ГОТОВО-КОГДА: файл internal/controlplane/dashboard_http_test.go
ГОТОВО-КОГДА: команда python3 -m unittest pilot.test_pilot.ReleaseTrainDashboardTests

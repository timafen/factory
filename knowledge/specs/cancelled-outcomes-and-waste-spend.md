# Спецификация: отдельные отмены и расход по причине исхода

## Цель и влияние на владельца

На Overview «Сделано недавно» перестаёт называть отменённую работу провалом:
владелец отдельно видит настоящие неудачи и отмены с понятной причиной. Блок
«Расход» перестаёт считать потраченное впустую только потому, что у terminal
задачи была ненулевая стоимость. Впустую — это неуспешная работа или остановка
системой по технической причине; сознательная остановка владельцем,
замена/дубликат и отменённый возврат либо исправление не искажают показатель.

Новые отмены сохраняют причину и инициатора как факты исхода. Официальные
причины: `owner_stopped`, `superseded_or_duplicate`,
`return_or_correction_cancelled`, `system_technical`, `unknown_legacy`.
Инициатор — `owner` либо `system`. `work_class`, `parent_task_id` и
`correction_kind` описывают вид и связь работы, а не причину отмены.

Для старых записей причина выводится только для отображения и расчёта в таком
порядке: (1) сохранённые причина и инициатор отмены; (2) сохранённое
автоматическое событие замены/дубликата; (3) структурные признаки старых
данных (`parent_task_id`/`correction_kind`) для отменённого возврата или
исправления; (4) `unknown_legacy`. Поэтому сохранённая отмена владельцем
побеждает даже при `parent_task_id` и `correction_kind`.

## Технический подход и реальные файлы

- `migrations/031_execution_cancellation_outcomes.sql` создаст append-only
  запись отмены для execution: `execution_id`, момент, валидируемые
  `reason`, `initiator` и машинный `trigger`. Очередная отмена без attempt
  тоже получает запись; повторный cancel не создаёт вторую запись. Старые
  строки намеренно не переписываются.
- `internal/protocol/types.go`, `internal/controlplane/state.go` и
  `internal/controlplane/store.go` добавят тип причины/инициатора в task
  detail и транзакционную запись исхода рядом с переводом execution в
  `cancelled`. Retry начинает новое актуальное состояние, но журнал прежней
  отмены остаётся доступным для аудита.
- `internal/controlplane/http.go` сохранит ручную отмену как
  `owner_stopped`/`owner`; внутренние вызовы Pilot будут передавать только
  допустимые системные причины. Сервер отвергает неизвестные пары, а клиент
  не может подменить ручную отмену технической классификацией.
- `pilot/pilot.py` передаст точные причины из уже известных точек: замена
  нездорового worker — `superseded_or_duplicate`, диагностический и
  budget-stop — `system_technical`; необъяснённые старые записи останутся
  `unknown_legacy`. `recent_done_block` вернёт три независимые группы
  `merged`, `failed`, `cancelled`, применит порядок классификации и даст
  отмене человекочитаемую причину.
- Там же `write_dashboard` заменит проверку состояния с ненулевой стоимостью
  на единую функцию классификации расхода. В `wasted_usd` входят `failed` и
  `cancelled/system_technical`; owner/superseded/correction не входят.
  Неизвестные legacy-отмены не выдаются за потери: их сумма выйдет отдельным
  `unclassified_cancelled_usd` и будет явно подписана в снимке.
- `pilot/test_pilot.py` закрепит приоритет причины, раздельные recent-группы
  и все ветви расчёта расхода.
- `web/src/Overview.tsx` расширит контракт Dashboard и покажет в «Сделано
  недавно» независимый блок «Отменены» с причиной, отличимый от «Провалы»;
  блок расхода пояснит неучтённые legacy-отмены без утверждения, что они
  были потрачены впустую.
- `web/src/Overview.test.ts` закрепит русские заголовки, причину отмены и
  отсутствие смешения с failed. `internal/controlplane/store_test.go` и
  `internal/controlplane/http_test.go` покроют durable-исход, идемпотентность
  и серверное назначение ручной причины.

## Последовательный план

1. Добавить миграцию и protocol-модель исхода отмены; провести её через все
   выборки task detail без изменения смысла `work_class` и provenance.
2. Сделать `CancelTask` принимающим серверную классификацию: ручной HTTP
   маршрут присваивает owner-причину, а внутренний путь Pilot — точную
   системную. Запись и terminal-переход выполняются одной транзакцией.
3. Вынести в Pilot чистую классификацию отмены и правила расхода; заменить
   текущую общую корзину failed/cancelled на `failed` и `cancelled`.
4. Передать корректные trigger/reason из queue rescue, diag repair и
   budget-stop; остальные вызовы явно выбрать и покрыть тестом, а не
   получать неявную причину из work metadata.
5. Обновить Overview контракт, доступные подписи и регрессии backend/Pilot/UI.
6. Выполнить целевые проверки, затем на Verify — общий набор проекта.

## Критерии приёмки

- Dashboard возвращает и Overview показывает раздельные `failed` и
  `cancelled`; отменённая задача не попадает в «Провалы».
- Каждая новая отмена сохраняет допустимые причину и инициатора. Ручная
  отмена получает `owner_stopped`/`owner`; автоматическая замена или дубликат
  получает `superseded_or_duplicate`/`system`.
- Явный исход имеет приоритет над автоматическим событием и legacy-признаками;
  сохранённая отмена владельцем не превращается в correction.
- Старое отменённое исправление получает только display fallback
  `return_or_correction_cancelled`; прочая старая отмена — `unknown_legacy`.
  `work_class` никогда не является таким fallback.
- Суточный `wasted_usd` включает расходы failed и технических system-cancelled,
  исключает owner/superseded/correction и не включает unknown legacy.
  Сумма неизвестных legacy-отмен возвращается и подписана отдельно.
- Повторная отмена идемпотентна: terminal state и единственная запись исхода
  не меняются; retry не переписывает исторический исход.

## Тест-план

- `internal/controlplane/store_test.go`: queued и running отмены создают один
  durable outcome; повтор не дублирует его; retry не стирает журнал.
- `internal/controlplane/http_test.go`: POST cancel назначает только
  `owner_stopped`/`owner`, а неприемлемая системная пара отвергается.
- `pilot/test_pilot.py`: table-driven матрица всех пяти причин, precedence
  owner-over-correction, автоматическая замена, legacy correction и unknown;
  проверка трёх independent recent limits.
- Тот же тест Pilot проверяет расход с ненулевой ценой для failed, пяти
  категорий отмен и нулевой цены: в `wasted_usd` остаются только failed и
  system_technical, unknown виден только как unclassified.
- `web/src/Overview.test.ts`: snapshot с failed и cancelled одновременно
  рисует «Провалы» и «Отменены», человеческую причину и не показывает
  внутренние enum/API ID.
- Обязательная целевая команда: `python3 -m unittest pilot.test_pilot.RecentDoneTest`.

## Риски и решения

- **Ложная историческая уверенность.** Не backfill-ить структурную догадку в
  durable причину: она только projection для legacy, а неизвестная сумма
  остаётся отдельной.
- **Подмена мотива типом работы.** Центральная classifier-функция принимает
  `work_class` лишь для отбора product results, не для причины или waste.
- **Гонка cancel/retry.** Outcome и смена terminal state пишутся одной
  транзакцией; повторный cancel читает уже записанный outcome.
- **Новая системная причина без учёта.** Enum/check constraint и unit-тест
  заставляют выбрать категорию, прежде чем новый Pilot cancel-path станет
  источником dashboard-данных.
- **Несовместимость старых снимков Dashboard.** Overview трактует
  отсутствующий `cancelled` как пустой массив и не считает неизвестный расход
  потерей до появления поля.

## Карточка работы

Карточка текущей работы: `knowledge/cards/CARD-0301-separated-cancellation-outcomes.md`.
Это этап Specification: implementation commit будет добавлен в начало карточки
реальным кодовым SHA на этапе Implement, до передачи карточки в Review.

ГОТОВО-КОГДА: файл migrations/031_execution_cancellation_outcomes.sql
ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл internal/controlplane/store.go
ГОТОВО-КОГДА: файл internal/controlplane/http.go
ГОТОВО-КОГДА: файл internal/controlplane/store_test.go
ГОТОВО-КОГДА: файл internal/controlplane/http_test.go
ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл web/src/Overview.tsx
ГОТОВО-КОГДА: файл web/src/Overview.test.ts
ГОТОВО-КОГДА: команда python3 -m unittest pilot.test_pilot.RecentDoneTest

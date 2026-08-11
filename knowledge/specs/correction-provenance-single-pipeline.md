# Спецификация: одна корректировка не создаёт второй конвейер

## Цель и влияние на владельца

При включённом Pilot задача-доработка после неуспешных Review или Verify должна
оставаться частью исходной работы. Она может выполняться, снова пройти Review и
Verify, влиться и закрыть исходную работу, но не может быть принята за новую
владельческую задачу и запустить ещё один пятистадийный конвейер.

Исторический сбой возникает потому, что `pilot/pilot.py:record_new_works()`
считает любую свежую неизвестную задачу с префиксом `[auto]` новой работой от
владельца. При этом `handle_answers()`, возвраты `review_gate`, повтор после
сбоя и другие correction-пути создают задачу через `POST /api/v1/tasks` без
машинного происхождения. Заголовок одновременно служит отображением и
неявным идентификатором, поэтому после потери локальной памяти или рестарта
корректировка может стать вторым корнем.

После изменения источник истины — сохранённая control-plane provenance, а не
строка заголовка. Владелец видит одну работу и одну историю, не получает шторм
дубликатов и не оплачивает параллельное повторение тех же пяти стадий. Эта
поставка не включает Pilot: сервис остаётся отключён до поставки данного
контракта и отдельной безопасной логики выпуска.

## Технический подход и реальные файлы

### Схема и миграция

Добавить `migrations/027_task_provenance.sql` с тремя nullable-колонками в
`tasks`:

- `work_id TEXT` — устойчивый идентификатор исходной работы;
- `parent_task_id TEXT REFERENCES tasks(id) ON DELETE SET NULL` — задача, из
  которой создано продолжение или исправление;
- `correction_kind TEXT` — причина возврата, допустимые значения
  `review_return`, `verify_return`, `machine_gate_return`, `execution_retry`,
  `merge_conflict_return`, `answer_resume` и `diagnostic_repair`.

Миграция 027 имеет жёсткую зависимость от
`026_worker_capacity_reconciliations.sql` из CARD-0085. До первого `ALTER` она
читает все контрактные поля `worker_capacity_reconciliations`; поэтому база на
025 без 026 завершает транзакцию ошибкой, не получает provenance-колонки и не
продвигает ledger. Runner берёт версию из числового префикса имени, поэтому 027
никогда не записывается как версия 26 при дырке в наборе файлов.

Создать индекс `tasks_work_created(work_id, created_at, id)` и индекс
`tasks_parent_task(parent_task_id)`. Старые строки не обновлять: три `NULL`
однозначно означают legacy-запись и позволяют ограниченный совместимый разбор
заголовка. Это важнее фиктивного backfill `work_id=id`, который ошибочно
превратил бы каждую старую стадию в отдельную работу.

`work_id` не является внешним ключом: он обязан пережить допустимое удаление
родительской истории. `parent_task_id` при удалении становится `NULL`, но
`work_id` и `correction_kind` сохраняются, поэтому потомок не становится новым
корнем. Ограничение допустимых `correction_kind` задаётся `CHECK`; связь полей
и репозитория проверяет транзакция `CreateTask`.

### API и хранение

В `internal/protocol/types.go` добавить к `CreateTaskRequest` поля
`parent_task_id` и `correction_kind`, а к `Task` — read-only ответы `work_id`,
`parent_task_id`, `correction_kind`. Неизвестные поля по-прежнему отклоняются.
Отсутствие новых полей остаётся совместимым запросом на создание корня.

В `internal/controlplane/store.go` внутри той же транзакции создания задачи:

1. Для запроса без `parent_task_id` запретить `correction_kind`, создать
   задачу-корень и записать `work_id = task.id`.
2. Для запроса с `parent_task_id` прочитать родителя, потребовать тот же
   `repository_id`, вычислить `work_id = COALESCE(parent.work_id, parent.id)` и
   записать его вместе с родителем и причиной.
3. Если `correction_kind` задан без родителя, неизвестен, родитель отсутствует
   либо репозиторий отличается — вернуть 400 с устойчивыми кодами
   `correction_parent_required`, `invalid_correction_kind`,
   `parent_task_not_found`, `parent_repository_mismatch`; запись не создавать.
4. Повтор того же `request_key` вернуть существующую задачу с исходной
   provenance. Как и сейчас, replay не мутирует сохранённую строку.
5. Расширить все проекции `scanTask`, `Tasks` и `Task`; list и detail обязаны
   возвращать одинаковые значения, чтобы Pilot не делал дополнительный запрос
   только ради классификации.

В `internal/controlplane/http.go` сохранить прежние 201/200 для create/replay
и добавить к существующему structured log создания `work_id`,
`parent_task_id`, `correction_kind`. В `internal/controlplane/automation_runtime.go`
новые Automation-корни записывают `work_id=taskID`; импортированные legacy
задачи остаются с `NULL`. В `internal/controlplane/work_resume_http.go` ручное
возобновление передаёт найденную исходную задачу как parent; запросы выборки
обновляются под расширенный `scanTask`.

### Алгоритм Pilot

В `pilot/pilot.py` ввести единый builder создания потомка, который принимает
объект исходной задачи и обязательно передаёт `parent_task_id`; для возврата
также обязательно передаёт `correction_kind`. Через него провести:

- обычный переход на следующую стадию и продолжение `pipeline_watch` — parent
  задан, `correction_kind` отсутствует;
- возврат Review в Implement — `review_return`;
- возврат Verify в Implement — `verify_return`;
- `review_gate`/Specification gates — `machine_gate_return`;
- инфраструктурный или повторный запуск упавшего этапа — `execution_retry`;
- возврат после конфликта слияния — `merge_conflict_return`;
- возобновление ответа после Review/Verify сохраняет `review_return` или
  `verify_return`; ответ после иного остановленного этапа и diagnostic repair —
  соответственно `answer_resume` и `diagnostic_repair`.

Новый корень определяется только как задача с непустым `work_id`, равным её
`id`, без `parent_task_id` и `correction_kind`. Любая новая задача с parent или
correction не проходит `record_new_works`, даже если её title начинается
`[auto]`, совпадает с новой стадией или изменён человеком. Для записей, у
которых все три поля `NULL`, сохраняется нынешний разбор `PIPELINE_TITLE` и
`base_title`; этот fallback помечается как legacy и никогда не переопределяет
явную provenance.

Группировку, дедупликацию стадий, `live_or_done_at`, `stage_attempts`,
`pipeline_watch`, вопросы и запись завершения перевести на `work_id` при его
наличии. Ключ локальной `works.json` для новых задач — `work_id`; человекочитаемый
base title хранится атрибутом. Поэтому рестарт, одинаковые заголовки и
корректировка заголовка не создают другую работу. Legacy-группы продолжают
работать по прежнему base title.

Когда root discovery встречает correction-задачу, которую прежний алгоритм
принял бы за свежий `[auto]` root, Pilot пишет
структурированное событие
`pilot_duplicate_root_prevented` с `task_id`, `work_id`, `parent_task_id` и
`correction_kind`. Идентификатор задачи запоминается в durable state Pilot,
поэтому событие считается один раз и доступно в journal после рестарта. Это
наблюдаемое доказательство защиты; отсутствие нового Triage остаётся основным
функциональным доказательством.

## Последовательный план

1. Добавить миграцию 027, ограничения и индексы; проверить открытие как новой,
   так и БД, остановленной на миграции 025.
2. Расширить protocol, `CreateTask`, list/detail/replay и structured create-log;
   добавить тесты валидации и сохранения после закрытия/повторного открытия БД.
3. Обновить прямое создание Automation и серверное возобновление работы, чтобы
   новые задачи не обходили контракт.
4. В Pilot добавить provenance-aware identity и единый child/correction builder,
   затем перевести все перечисленные места создания задач.
5. Перевести учёт work/stage/question/merge на `work_id`, оставив title fallback
   только для строк с полностью отсутствующей provenance.
6. Добавить регрессию исторического шторма, событие предотвращения и сценарий
   рестарта; прогнать целевые Go/Python тесты и общий `pilot.test_pilot`.
7. Выпустить control plane с миграцией, затем новый Pilot, оставляя Pilot
   остановленным. Включение разрешено только после одновременного наличия этой
   версии и отдельной безопасной release state machine.

## Критерии приёмки

1. Новый root через старое тело `POST /api/v1/tasks` создаётся как раньше и в
   list/detail имеет `work_id == id`, пустые parent/correction.
2. Потомок наследует `work_id` родителя; correction без валидного parent,
   неизвестного вида или в другом репозитории атомарно отклоняется.
3. Provenance одинакова после API replay и после закрытия/повторного открытия
   SQLite; мигрированная legacy-задача читается с пустыми новыми полями.
4. Failed Review/Verify создаёт ровно одну Implement-корректировку с
   `review_return`/`verify_return`, затем она может пройти Review, Verify,
   merge и завершить исходный `work_id`.
5. `record_new_works` не регистрирует correction как новый root и не создаёт
   Triage/Specification для неё; title не влияет на решение при заполненной
   provenance.
6. В воспроизведении шторма до и после рестарта существует ровно один root
   `work_id` и ровно один пятистадийный pipeline; число созданных root/Triage
   задач не увеличивается.
7. Для отвергнутой root-классификации появляется ровно одно событие
   `pilot_duplicate_root_prevented` с четырьмя идентификаторами; повторный цикл
   и рестарт не дублируют событие. Полная запись остаётся в durable outbox по
   стабильному event ID при сбоях до/после append и acknowledgement.
8. Старые задачи и старые клиенты остаются читаемыми/работоспособными; title
   fallback применяется только к legacy-строкам с тремя `NULL`.
9. База 025 с одной 027 атомарно отказывается обновляться; 025 + 026 + 027
   обновляется до версии 27 и безопасно открывается повторно. Rollback бинарника
   допустим: старый код игнорирует nullable-колонки; миграция не откатывается.
10. Реализация не включает Pilot. До поставки безопасной release state machine
    и прохождения smoke Pilot остаётся отключён операционно.

## Тест-план

- `internal/controlplane/store_test.go`:
  `TestTaskProvenanceValidationAndReplay` проверяет root/child/correction и
  коды ошибок; `TestTaskProvenancePersistsAcrossReopenAndParentDelete` —
  replay, удаление parent, повторное открытие SQLite;
  `TestTaskProvenanceMigrationRequires026AndReopensSafely` проверяет отказ
  025 + 027 без изменения схемы/ledger и успех 025 + 026 + 027 с reopen.
- `internal/controlplane/http_test.go`:
  `TestTaskProvenanceHTTPCompatibilityAndLogging` проверяет старое create-body,
  новые JSON-поля в list/detail, 400-коды и structured log provenance.
- `pilot/test_pilot.py`, класс `CorrectionProvenanceStormTests`: создать root,
  довести до failed Review и answered correction, дважды вызвать discovery,
  пересоздать in-memory Pilot с теми же API-данными/durable state и довести
  correction через Review/Verify/merge. Проверить один root, один pipeline,
  отсутствие второго Triage и одно prevented-событие до и после рестарта.
- В этом классе параметризованный тест
  `test_review_and_verify_corrections_complete_one_pipeline_after_restart`
  воспроизводит обе исторические точки возврата через `handle_answers`,
  сохранение/пересоздание state, реальные циклы Review/Verify и merge; тест
  `test_explicit_provenance_wins_over_auto_title` запрещает title-only решение.
- `test_duplicate_root_outbox_converges_at_every_crash_boundary` проверяет
  сбой до записи, после append и до/после acknowledgement: durable event один.
- Там же параметризовать Review и Verify, заголовки `[auto]`, изменённый title и
  одинаковые base title у двух разных `work_id`; явная provenance всегда
  побеждает строку.
- Сохранить legacy-регрессии `record_new_works`, `pipeline_watch`, resume,
  Review/Verify returns и прогнать весь `python3 -m unittest -v pilot.test_pilot`.

## Риски и решения

- Между локальным состоянием Pilot и SQLite раньше не было общего ID работы.
  Решение: control plane назначает/наследует `work_id` транзакционно; Pilot его
  не генерирует и не восстанавливает из title.
- `ON DELETE SET NULL` мог бы сделать потомка похожим на root. Решение: root
  требует одновременно `work_id == id` и пустой correction; сохранённые
  `work_id`/kind продолжают исключать correction.
- Частичный rollout: старый Pilot не отправляет parent. Поэтому сначала
  выкатывается совместимый control plane, затем новый Pilot при остановленном
  сервисе; включать между этими шагами запрещено.
- Полный backfill старых цепочек по заголовку ненадёжен. Решение: не менять
  legacy-строки и изолировать эвристику только в совместимом пути.
- Новое перечисление может забыть редкий return-path. Единый builder и тест,
  который запрещает прямое создание `[auto]`-потомка без parent, делают такой
  пропуск видимым.
- Rollback схемы разрушителен и не нужен. Старый бинарник работает с лишними
  nullable-колонками; откат выполняется только бинарником, данные сохраняются.

## Rollout, rollback и вне области

До появления CARD-0085/026 в `main` эта ветка намеренно не подлежит merge или
release. После снятия зависимости rollout: backup SQLite; миграция и control plane; API smoke root/child/read;
Pilot binary; storm-тест на копии данных; проверка journal-события; только затем
отдельное решение о включении после поставки safe release logic. При ошибке
остановить Pilot и вернуть предыдущий бинарник, не удаляя migration 027.

Вне области: включение Pilot, реализация безопасного release/rollback автомата,
изменение UI, переименование существующих задач, восстановление точных цепочек
для legacy-истории, изменение лимитов повторов и исправление старой CARD-0079.

## Карточка работы

`knowledge/cards/CARD-0086-correction-provenance-single-pipeline.md`

Реализация строгой коррекции: `aa05c7eb3c01e665609bc847b0f493f35edd10f9`.

Номер 0086 выбран после `git fetch` и проверки свежего `origin/main` и всех
опубликованных `factory/*`: предыдущий номер уже занят параллельной работой, а
CARD-0086 отсутствует. Карточка относится только к этой работе; конфликтная
старая CARD-0079 не используется.

ГОТОВО-КОГДА: файл migrations/027_task_provenance.sql
ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл internal/controlplane/store.go
ГОТОВО-КОГДА: файл internal/controlplane/http.go
ГОТОВО-КОГДА: файл internal/controlplane/automation_runtime.go
ГОТОВО-КОГДА: файл internal/controlplane/work_resume_http.go
ГОТОВО-КОГДА: файл internal/controlplane/store_test.go
ГОТОВО-КОГДА: файл internal/controlplane/http_test.go
ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: команда go test ./internal/controlplane && python3 -m unittest -v pilot.test_pilot.CorrectionProvenanceStormTests

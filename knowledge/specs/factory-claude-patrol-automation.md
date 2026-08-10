# Перенос патруля Claude в Factory Automations с историей запусков

## Цель и влияние на пользователя

Владелец запускает уже существующий пробный патруль конвейера как Factory
Automation по его имеющемуся расписанию, а не из отдельного `pilot`-цикла.
Каждое срабатывание — scheduled или ручное — остаётся в истории Automation с
временем, диагностикой и созданной Task; из списка Automations можно открыть
сам результат. Это делает работу патруля наблюдаемой и не меняет его смысл:
он продолжает только канонические `[auto] [N/M Stage]` конвейеры, ждёт перед
повторным толчком, не трогает паузу владельца и эскалирует после лимита попыток.

Источником задания является `pipeline_watch` в `pilot/pilot.py`, как подтвердил
владелец. Внешнего prompt, ссылки, cron и часового пояса в контракте нет, поэтому
новые проверки и значения расписания не добавляются.

## Технический подход

Сохранить текущую типизированную модель schedule Automation, а не вводить новый
триггер или отдельную таблицу истории. `internal/controlplane/schedule_runtime.go`
уже записывает одну durable `automation_occurrence` на каждый due instant и на
`Run now`, сохраняет prompt-снимок, а затем привязывает созданную Task. UI в
`web/src/Automations.tsx` уже показывает эти Occurrences в разделе Runs.

Добавить идемпотентный provisioning/migration путь для единственного встроенного
патруля: он находит уже имеющиеся workflow и schedule Automation, переносит в
workflow instructions и automation context смысл `pipeline_watch`, включает
Automation только после успешного связывания и не создаёт второй экземпляр при
повторном запуске. Патруль получает лишь снимок Factory (задачи, workflows,
workers и ранее сохранённое состояние) и создаёт следующий этап теми же
`workflow_revision_id`, `repository_id`, timeout и маршрутизацией worker, что и
сегодня. Состояние паузы/ожидания/двух толчков должно быть durable, а не
`pilot/stalled.json`, чтобы перезапуск control-plane не стирал ход патруля.

Затрагиваются:

- `internal/controlplane/…`: provisioning встроенного Automation и durable
  состояние патруля; использование существующего Schedule Occurrence/Task
  linkage без изменения публичной формы истории;
- `internal/controlplane/*_test.go`: создание, due dispatch, повторный запуск
  provisioner и сценарии патруля через Automation;
- `pilot/pilot.py` и `pilot/test_pilot.py`: убрать вызов старого `pipeline_watch`
  из цикла и его тестовый контракт после того, как Automation становится
  единственным исполнителем;
- `web/src/Automations.tsx` и связанный тест — только если текущий экран не
  различает результат патруля и его Task; нового экрана и API не требуется.

Публичные Automation API, схема Schedule Trigger и формат `AutomationOccurrence`
не меняются. Новая миграция допустима только для durable состояния патруля или
идемпотентной регистрации встроенного Automation; она не должна создавать
расписание, если его точные данные отсутствуют в текущем Factory-состоянии.

## План

1. Зафиксировать извлечение состояния канонических pipeline-задач и переходов
   `pipeline_watch` в control-plane сервисе, включая 600-секундное ожидание,
   два толчка, owner pause, final stage и одиночное уведомление об остановке.
2. Добавить миграцию/хранилище durable patrol-state и идемпотентный provisioner,
   который использует существующие workflow, repository и schedule вместо
   выдуманных значений; повторение не меняет уже сохранённые Occurrences.
3. Выполнять патруль из scheduled Automation: создать историю срабатывания до
   работы, сохранить результат/диагностику и связать Task следующего этапа с
   соответствующей Occurrence.
4. Отключить вызов `pipeline_watch` из `pilot.cycle` только после успешного
   provisioner-пути, чтобы не было двух исполнителей одного патруля.
5. При необходимости уточнить в существующей строке Runs подпись результата
   патруля и добавить UI-регрессию; не менять общий UX Automations.

## Критерии приёмки

- Имеющееся расписание встроенного пробного патруля создаёт ровно одно durable
  scheduled Occurrence на instant и ровно одну привязанную Task для допустимого
  потерянного перехода; повтор обработки не дублирует ни запись, ни Task.
- В Details → Runs видно каждый scheduled и Run now запуск патруля, его время,
  итог/диагностику и переход к созданной Task, включая неуспешный запуск без Task.
- Смысл текущего патруля сохранён: он учитывает только канонические заголовки,
  ждёт 600 секунд, продолжает с прежними repository/revision/worker, не трогает
  owner pause и финальный этап, а после двух неудачных толчков эскалирует один раз.
- Перезапуск control-plane не стирает ожидание, число толчков или зафиксированный
  результат запуска; legacy `pilot`-цикл больше не выполняет второй patrol-run.
- Если нужные workflow, repository или schedule не найдены, provisioner честно
  сообщает blocked/diagnostic и не создаёт Automation с угадываемым расписанием.

## План тестирования

- Добавить Go-тест с fake clock: provisioner использует существующее расписание;
  due instant создаёт единственную Occurrence, затем Task и отображаемый результат;
  повтор/рестарт сохраняет историю.
- Добавить сценарии патруля для ожидания, дедупликации живой задачей, owner pause,
  final stage и двух толчков; проверять snapshot repository/revision/worker.
- Обновить Python-тест цикла, чтобы он подтверждал отсутствие вызова legacy
  `pipeline_watch` после переноса.
- Если меняется подпись Runs, добавить узкий React-тест этого результата.
- Обязательная команда: `go test ./internal/controlplane -run 'Test.*(Schedule|Patrol)'`.
- Регрессии: `python3 -m unittest pilot.test_pilot` и, только при UI-изменении,
  `npm --prefix web test -- --run Automations`.

## Риски и решения

- Точный cron, часовой пояс и идентификаторы существующих workflow/repository не
  находятся в репозитории. Решение: implementation читает/связывает уже
  зарегистрированное состояние и останавливается с диагностикой, а не назначает
  значения. Человеку нужно подтвердить место, где эти runtime-данные создаются,
  если provisioner его не видит.
- Automation сегодня создаёт одну Task с workflow prompt, а `pipeline_watch`
  непосредственно создаёт следующий этап. Нужно подтвердить, что результатом
  Automation может быть агентский patrol-task, либо согласовать минимальный
  control-plane executor; не следует маскировать это изменением prompt.
- Нельзя одновременно оставлять `pilot.pipeline_watch` и Automation: два
  исполнителя смогут создать дубли. Переключение производится атомарно после
  проверки provisioned Automation.
- Не расширять задачу до общего переноса всех pilot-функций, нового cron-редактора
  или миграции исторических JSON-записей: они вне подтверждённого объёма.

## Карточка

`knowledge/cards/CARD-0045-factory-claude-patrol-automation.md`

ГОТОВО-КОГДА: файл internal/controlplane/pipeline_patrol.go
ГОТОВО-КОГДА: файл internal/controlplane/pipeline_patrol_test.go
ГОТОВО-КОГДА: файл internal/controlplane/schedule_runtime.go
ГОТОВО-КОГДА: файл internal/controlplane/schedule_automations_test.go
ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run 'Test.*(Schedule|Patrol)'

# Патрули и их находки на экране «Автоматизации»

## Цель и влияние на владельца

Встроенные патрули Factory должны перестать выглядеть как продуктовые работы:
их активные и завершённые запуски не попадают ни в список, ни в режим «по
этапам» экрана «Работа». Владелец наблюдает каждый патруль там, где ожидает
автоматику: в истории запусков соответствующей Automation, вместе с
фактическим состоянием, итогом последней попытки и явно отмеченными находками.

Обычные работы и пользовательские scheduled Automation остаются на прежних
экранах. Если исполнитель не сохранил результат или ошибку, интерфейс честно
показывает «Результат не оставлен» и не придумывает успешную проверку.

## Технический подход и реальные файлы

### Единая классификация для экрана «Работа»

`internal/controlplane/work_classification.go` уже распознаёт класс `patrol`
только по устойчивым фактам: задача связана с scheduled Automation, а её
сохранённые title/context содержат канонический маркер
`factory pipeline patrol`. Заголовок Task не участвует в распознавании.

В `internal/protocol/types.go` списочная `Task` получает аддитивное поле
`work_class`. `internal/controlplane/store.go` присоединяет occurrence,
Automation и schedule trigger в `Store.Tasks`, после чего вызывает существующий
`classifyWork`. `internal/controlplane/work_classification_test.go` фиксирует
патруль, обычное расписание и пользовательскую задачу с похожим названием.

`web/src/types.ts` принимает новый контракт. `web/src/Work.tsx` исключает
`work_class === "patrol"` до группировки и формирования представлений, поэтому
патруль не остаётся ни в карточках, ни в архиве, ни в режиме «по этапам».
Регрессии покрывают `web/src/Work.test.ts` и `web/src/WorkView.test.tsx`.
Подпись успешной Task без настоящего verdict меняется с «проверка пройдена» на
«задача выполнена»; принятый `final_pass` сохраняет прежний смысл.

### Результат запуска на экране «Автоматизации»

Источником остаются сохранённые `attempts.result` и `attempts.error`, которые
уже читает `pilot/pilot.py::collect_automation_findings`; новая таблица не
нужна. В `internal/protocol/types.go` occurrence получает необязательные
`attempt_state`, `result` и `error`. `internal/controlplane/automations.go`
выбирает одну последнюю попытку связанного execution по attempt number с
детерминированной развязкой по времени и ID. Это сохраняет правило «один
occurrence — одна строка» и курсорную пагинацию.

`internal/controlplane/schedule_automations_test.go` проверяет пустую попытку,
первую ошибку, retry, результат второй попытки и HTTP-проекцию. В
`web/src/automationOccurrence.ts` отдельно размещаются чистые функции: строки
с префиксом `НАХОДКА:` извлекаются из result с поддержкой LF/CRLF, а итогом
служит полный result, затем error, затем нейтральная заглушка.
`web/src/Automations.tsx` показывает badge фактического состояния, находки и
итог; `web/src/Automations.test.tsx` проверяет разбор без зависимости от React.
После сборки обновляются отслеживаемые `web/dist/index.html` и hashed bundle.

## Последовательный план

1. Расширить Go- и TypeScript-модели аддитивными read-only полями.
2. Проецировать `work_class` из durable Automation/schedule-фактов в список
   Tasks и покрыть положительный случай и исключения.
3. Исключить только патрули до построения обоих представлений «Работы» и
   исправить ложную подпись успеха.
4. Проецировать последнюю попытку в occurrence без дубликатов и проверить
   empty/error/retry/result через Store и HTTP API.
5. Вынести разбор находок/итога, отрисовать их в истории Automation, добавить
   UI-регрессии и пересобрать embedded web assets.

## Критерии приёмки

- Встроенный Factory Pipeline Patrol не виден в списке, архиве, «Сделано» и
  режиме «по этапам» экрана «Работа» во всех состояниях задачи.
- Похожий Task title не скрывает пользовательскую работу; обычная scheduled
  Automation и несвязанная Task сохраняются без изменений.
- Каждый Automation-run показывает фактическое состояние, полный итог
  последней попытки и все непустые строки с точным префиксом `НАХОДКА:`.
- Failed-run показывает сохранённую ошибку, а run без result/error —
  «Результат не оставлен» без выдуманной находки.
- Retry не размножает occurrence: после повторной попытки отображаются данные
  именно последней попытки, а существующий retry badge продолжает работать.
- Простое `succeeded` без `final_pass` называется выполненной задачей, а не
  пройденной проверкой.

## Тест-план

- `go test ./internal/controlplane -run
  'TestTasksWorkClassUsesAutomationFacts|TestAutomationOccurrenceProjectsAttemptOutputAcrossRetryAndAPI'`
  — классификация и серверная проекция empty/error/retry/result.
- `cd web && npm test -- --run src/Work.test.ts src/WorkView.test.tsx
  src/Automations.test.tsx` — оба режима «Работы», обычные задачи, находки и
  нейтральный итог.
- `cd web && npm run typecheck && npm run lint && npm run build` — контракты,
  lint и воспроизводимость embedded bundle.
- На Verify открыть `/work`, переключить «Показать по этапам», затем открыть
  detail `/automations/<id>` патруля с успешным, ошибочным и пустым запуском.

## Риски и решения

| Риск | Решение |
| --- | --- |
| Ложное совпадение по слову Patrol | Не анализировать Task title; использовать существующий `classifyWork` и Automation/schedule-факты. |
| JOIN изменит размер страницы Tasks или occurrence | Связи occurrence/task уникальны; последнюю attempt выбирать одиночным коррелированным подзапросом, порядок и API закрепить тестом. |
| Старый occurrence не имеет Task или attempt | Поля оставить необязательными и показывать нейтральный итог. |
| Error будет выдан за находку | Находки брать только из result и только по точному построчному префиксу; error показывать итогом. |
| Экспорт helpers вызовет warning React Fast Refresh | Держать чистые функции в отдельном `automationOccurrence.ts`. |
| Production UI разойдётся с исходниками | Выполнить web build и зафиксировать обновлённые `web/dist` assets. |

## Карточка работы

Карточка: `knowledge/cards/CARD-0171-patrol-findings-on-automations.md`.
Номер свободен в свежем `origin/main` и во всех опубликованных ветках на
момент подготовки Specification. Предыдущие CARD-0129/CARD-0137 принадлежат
другой ветке работы и не переиспользуются.

ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл internal/controlplane/store.go
ГОТОВО-КОГДА: файл internal/controlplane/automations.go
ГОТОВО-КОГДА: файл internal/controlplane/work_classification_test.go
ГОТОВО-КОГДА: файл internal/controlplane/schedule_automations_test.go
ГОТОВО-КОГДА: файл web/src/types.ts
ГОТОВО-КОГДА: файл web/src/Work.tsx
ГОТОВО-КОГДА: файл web/src/Work.test.ts
ГОТОВО-КОГДА: файл web/src/WorkView.test.tsx
ГОТОВО-КОГДА: файл web/src/automationOccurrence.ts
ГОТОВО-КОГДА: файл web/src/Automations.tsx
ГОТОВО-КОГДА: файл web/src/Automations.test.tsx
ГОТОВО-КОГДА: файл web/dist/index.html
ГОТОВО-КОГДА: файл web/dist/assets/index-AUueY2nO.js
ГОТОВО-КОГДА: команда cd web && npm test -- --run src/Work.test.ts src/WorkView.test.tsx src/Automations.test.tsx

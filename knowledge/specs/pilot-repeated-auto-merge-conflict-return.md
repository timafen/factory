# Pilot повторно возвращает работу после каждого AUTO-MERGE-конфликта

## Цель и влияние на владельца

Если исправленная после первого AUTO-MERGE-конфликта ветка снова проходит
Review и Verify, но GitHub обнаруживает новый content conflict, Pilot должен
создать новый возврат в `Implement + Test`. Первый `merge_conflict_return`
относится только к первому конфликту и не имеет права подавлять следующий
раунд исправления.

Для владельца это означает, что доставка не застывает после повторного
расхождения с `main`: та же работа и та же delivery-ветка автоматически снова
попадают к исполнителю, затем заново проходят Review и Verify. При этом один и
тот же конфликт по-прежнему не создаёт дубликаты и не повторяет неизменённый
merge-запрос.

## Технический подход и реальные файлы

Фактический путь находится в `pilot/pilot.py`:

- финальный Verify создаёт `state["merge_intents"][verify_task_id]` с
  неизменяемым проверенным `commit_sha`;
- `recover_merge_intents()` переводит несливаемый intent в `phase=conflict`;
- `resume_merge_conflicts()` создаёт child-задачу с
  `correction_kind=merge_conflict_return`, после чего переводит только этот
  intent в `phase=repairing`.

Идемпотентность нужно явно ограничить поколением конфликта, а не всей работой.
Идентичность поколения — пара `(verify_task_id, commit_sha)`: новый проход
Verify имеет новый task id и новый проверенный head, поэтому обязан получить
собственный request key и собственный `repair_task_id`. Старые intents в
`repairing` остаются журналом предыдущих раундов, но не участвуют в поиске
возврата для нового `phase=conflict`.

В `resume_merge_conflicts()` поиск существующего возврата и durable-переход
должны быть привязаны к текущему conflict-intent: parent — именно текущий
Verify, correction kind — `merge_conflict_return`, а стабильный request key
строится из текущих `verify_task_id` и `commit_sha`. Повторный цикл или рестарт
для того же intent связывает уже созданную задачу; новый intent создаёт новую.
Глобальный счётчик возвратов работы и `cap_rescues` к этому пути не применяются.

Сохраняется текущая fail-safe семантика: отсутствие workflow, worker,
repository/branch, нехватка слота или ошибка Control Plane оставляют именно
новый intent в `conflict` для следующей попытки. `recover_merge_intents()` не
повторяет конфликтный merge и не переводит старый intent обратно в работу.

Реальные файлы реализации:

- `pilot/pilot.py` — поколенческая идемпотентность и привязка каждого
  conflict-intent к своему возврату;
- `pilot/test_pilot.py` — регрессия двух последовательных конфликтов в
  `MergeConflictRecoveryTests`.

UI, control-plane API, схема хранения, `pilot/config.example.json` и release
broker не требуют изменений: используются существующие поля task provenance
и `merge_intents`.

## Последовательный план

1. Зафиксировать в `resume_merge_conflicts()` идентичность поколения как
   текущие `verify_task_id` и `commit_sha`; не искать и не переиспользовать
   correction-задачу другого Verify той же работы.
2. Сохранить request key и `repair_task_id` только в соответствующем intent;
   оставить предыдущие intents в `repairing` без влияния на новый конфликт.
3. Сохранить exactly-once внутри поколения: повторный цикл, рестарт и повторный
   ответ create API не должны создавать вторую задачу для того же Verify/head.
4. Добавить целевой тест с двумя последовательными Verify-intents и проверить
   разные parent/request key/repair task, одинаковые work/repository/branch и
   отсутствие третьей задачи при повторном вызове.
5. Запустить новый тест, затем весь `MergeConflictRecoveryTests`; полный набор
   проекта оставить единственному этапу Verify.

## Критерии приёмки

- Первый AUTO-MERGE-конфликт создаёт один `merge_conflict_return` и переводит
  свой intent из `conflict` в `repairing`.
- После исправления, нового Review/Verify и нового AUTO-MERGE-конфликта
  создаётся второй `merge_conflict_return` с parent нового Verify; наличие
  первого возврата и старого `repairing` intent этому не мешает.
- Оба возврата сохраняют один `work_id`, repository и delivery-ветку, но имеют
  разные request key и `repair_task_id`, соответствующие своим Verify/head.
- Третий и последующие последовательные конфликты следуют тому же правилу без
  глобального ограничения числа поколений.
- Повторный цикл или рестарт в пределах одного conflict-intent не создаёт
  дубликат и не повторяет неизменённый `gh_merge`.
- Ошибка маршрута/API или временная нехватка ресурса оставляет новый intent в
  `conflict`; после восстановления создаётся именно его возврат.
- Реализация не создаёт новый корень работы, не запускает заново
  Triage/Specification и не меняет UI или внешний API.

## Тест-план

В `pilot.test_pilot.MergeConflictRecoveryTests` добавить тест
`test_repeated_conflict_creates_new_repair_generation`:

1. создать первый conflict-intent, вызвать `resume_merge_conflicts()` и
   получить `repair-1`;
2. оставить первый intent в `repairing`, добавить новый Verify с другим id и
   head в `phase=conflict`, затем вызвать recovery ещё раз;
3. доказать второй вызов `create_child_task()` с parent нового Verify,
   `correction_kind=merge_conflict_return`, новым request key и результатом
   `repair-2`;
4. доказать, что work/repository/branch прежние, первый intent не перезаписан,
   а повторный вызов не создаёт `repair-3`;
5. повторить последний шаг после сериализации/загрузки state, чтобы покрыть
   рестарт.

Дополнительно существующий класс обязан сохранить проверки: conflict не
повторяет merge, один intent возвращается exactly once, correction после
рестарта связывается без дубля, недоступный маршрут ждёт следующего цикла и
сливаться может только новый проверенный head.

Текущий baseline выполнен командой
`python3 -m unittest -q pilot.test_pilot.MergeConflictRecoveryTests`: 8 тестов,
код 0. Он подтверждает первый возврат, но не выражает обязательный второй
раунд; поэтому новый именованный тест является приёмочной проверкой.

## Риски и решения

- **Старый возврат подавит новый.** Искать correction только по parent текущего
  Verify и идентичности текущего intent, не по `work_id`, title или наличию
  любого `merge_conflict_return` в истории.
- **Рестарт создаст дубль текущего раунда.** Сохранить стабильный request key
  из Verify/head и сначала связывать существующую child-задачу; Control Plane
  остаётся последней идемпотентной границей после сбоя между POST и `save()`.
- **История конфликтов будет перезаписана.** Не переиспользовать старый ключ
  `merge_intents`: каждый Verify остаётся отдельной audit-записью со своим
  `repair_task_id`.
- **Бесконечный системный конфликт сожжёт ресурсы.** Каждый новый возврат
  разрешён только после успешных Implement, Review и Verify с новым immutable
  head; неизменённый conflict-intent merge не повторяет. Политика отдельной
  остановки/эскалации может быть добавлена другой работой, но не должна
  превращать первый возврат в глобальный запрет.
- **Legacy state не содержит новых служебных полей.** Источниками идентичности
  остаются уже обязательные ключ словаря `verify_task_id` и `commit_sha`; для
  старых записей сохраняется текущая exactly-once семантика.

## Карточка работы

`knowledge/cards/CARD-0168-pilot-repeated-auto-merge-conflict-return.md` —
отдельная карточка этой спецификации. Номер и точный путь проверены по свежему
`origin/main` и опубликованным refs: заняты номера до CARD-0167 включительно,
CARD-0168 и выбранный путь свободны.

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: команда python3 -m unittest -q pilot.test_pilot.MergeConflictRecoveryTests.test_repeated_conflict_creates_new_repair_generation

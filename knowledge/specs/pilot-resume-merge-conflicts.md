# Pilot возвращает конфликт слияния в Implement + Test

## Цель и влияние на владельца

Если после успешных Review и Verify GitHub отклоняет слияние из-за content
conflict, Pilot должен зафиксировать это как техническую остановку и вернуть
ту же работу на ту же delivery-ветку в `Implement + Test`. Владелец не получает
новый корень, повторный Triage/Specification или бесконечные попытки того же
слияния. После исправления ветка снова проходит Review и Verify; конфликт не
может выглядеть как завершённая работа.

## Технический подход и реальные файлы

Источник истины — `state.json` Pilot: `merge_intents[verify_task_id]` хранит
`phase=conflict`, ветку, repository, проверенный head и короткий ответ GitHub.
`recover_merge_intents` при конфликтном ответе записывает эту фазу и не
повторяет `gh_merge`. В начале следующего цикла `resume_merge_conflicts`:

1. выбирает только intent с `phase=conflict` и проверяет, что маршрут содержит
   включённый `Implement + Test` с revision id;
2. находит исходную Verify-задачу (при необходимости через detail API), её
   repository и совместимого healthy worker;
3. создаёт ровно одну child-задачу на той же ветке с `parent_task_id` и
   `correction_kind=merge_conflict_return`, стабильным request key и контекстом
   для fetch origin/main, rebase/merge, разрешения конфликта, тестов и push;
4. переводит intent в `repairing` и сохраняет `repair_task_id`. При рестарте
   существующий child только связывается с intent, новая задача не создаётся.

После исправления обычные pipeline handoff должны сохранить work provenance;
только новый Verify PASS может сформировать новый merge intent. Отсутствие
workflow/worker/repository или ошибка создания оставляет intent в конфликте и
должно быть диагностируемым, без подмены работы и без уведомления о Done.

Реальные файлы реализации и тестов: `pilot/pilot.py`, `pilot/test_pilot.py`.
Эта спецификация не разрешает изменения UI, control-plane API, миграций или
release broker.

## Последовательный план

1. Сохранить переход `gh_merge failure(conflict) → merge_intent.conflict` до
   любой повторной попытки и покрыть его проверкой durable state.
2. Вынести/сохранить idempotent child-builder с обязательными parent и
   correction kind; передать delivery branch, verified head и GitHub reason.
3. Реализовать/проверить выбор Implement worker по тому же repository и
   готовности; не создавать задачу при недоступном маршруте.
4. Обновить цикл так, чтобы recovery выполнялся до cursor `processed` и до
   обычных handoff; после child вернуть intent в `repairing`.
5. Добавить сценарии повторного цикла, рестарта, отсутствующих ресурсов,
   другой ветки и повторного Verify → merge; прогнать целевой тест.

## Критерии приёмки

- Content conflict фиксируется durable intent с `phase=conflict`, GitHub reason
  сохраняется, а повторный `gh_merge` до ремонта не выполняется.
- Для одной Verify-задачи создаётся ровно одна задача `[3/5 Implement + Test]`
  на исходной ветке с тем же repository, parent и
  `merge_conflict_return`.
- Второй цикл и рестарт находят существующую correction-задачу и не создают
  дубликат; intent содержит её id и `phase=repairing`.
- Контекст ремонта требует актуальный `origin/main`, разрешение конфликта,
  полный обязательный тестовый набор и push той же ветки.
- После ремонта путь снова требует Review и Verify; конфликт не помечается
  выполненным, а новый merge допускается только для нового проверенного head.
- При выключенном workflow, отсутствующем worker/repository или ошибке API
  Pilot безопасно ждёт и сохраняет intent для следующего цикла.

## Тест-план

- `MergeConflictRecoveryTests.test_conflict_returns_same_work_to_implement_once`:
  создание, title, branch, parent, correction kind, state и идемпотентность.
- Тест recovery merge: GitHub content conflict записывается один раз и не
  вызывает второй merge.
- Тесты restart/missing worker/missing parent: intent не теряется и child не
  дублируется.
- Цикл после correction: Review/Verify выполняются перед новым merge intent.
- Обязательная проверка: `python3 -m unittest pilot.test_pilot.MergeConflictRecoveryTests`.

## Риски и решения

- Повтор цикла может породить шторм — стабильный request key, parent lookup и
  durable `repair_task_id` дают exactly-once.
- Старая ветка может быть force-pushed — перед дальнейшим merge заново
  проверять immutable verified head; при расхождении остановить merge.
- Worker может не иметь repository или capacity — не создавать заменяющую
  ветку, оставить intent в ожидании и записать причину.
- Ошибка после создания child до сохранения state — следующий цикл ищет child
  по parent и correction kind, затем восстанавливает phase.

## Карточка работы

`knowledge/cards/CARD-0127-pilot-resume-merge-conflicts.md`.

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: команда python3 -m unittest pilot.test_pilot.MergeConflictRecoveryTests

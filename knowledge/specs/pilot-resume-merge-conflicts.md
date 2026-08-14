# Pilot возвращает конфликт слияния в Implement + Test

## Цель и влияние на владельца

Если после успешных Review и Verify GitHub отклоняет слияние из-за content
conflict, Pilot должен зафиксировать это как техническую остановку и вернуть
ту же работу на ту же delivery-ветку в `Implement + Test`. Владелец не получает
новый корень, повторный Triage/Specification или бесконечные попытки того же
слияния. После исправления ветка снова проходит Review и Verify; конфликт не
может выглядеть как завершённая работа.

## Технический подход

Источник истины — `state.json` Pilot: `merge_intents[verify_task_id]` хранит
`phase=conflict`, ветку, repository, проверенный head и короткий ответ GitHub.
`recover_merge_intents` при конфликтном ответе записывает эту фазу и не
повторяет `gh_merge`. В начале следующего цикла `resume_merge_conflicts`:

1. выбирает только intent с `phase=conflict` и включённый `Implement + Test`;
2. находит исходную Verify-задачу, repository и совместимого healthy worker;
3. создаёт одну child-задачу на той же ветке с `parent_task_id`,
   `correction_kind=merge_conflict_return` и стабильным request key;
4. переводит intent в `repairing` и сохраняет `repair_task_id`.

После исправления обычный pipeline handoff сохраняет work provenance. Только
новый Verify PASS может сформировать новый merge intent. Отсутствие workflow,
worker, repository или branch, а также ошибка API оставляют intent в конфликте
для следующего цикла и не создают подменяющую работу.

## Критерии приёмки

- Content conflict сохраняется как durable `phase=conflict` вместе с причиной,
  а тот же `gh_merge` до ремонта не повторяется.
- Создаётся ровно одна `[3/5 Implement + Test]` на исходной ветке, с тем же
  repository, parent и `merge_conflict_return`.
- Повторный цикл и рестарт связывают существующую correction-задачу без дубля.
- Контекст требует свежий `origin/main`, разрешение конфликта, полный набор
  тестов и push той же ветки.
- Старый конфликт не считается выполненным; merge разрешён только новому
  Verify intent с новым проверенным head.
- Недоступный маршрут или API безопасно оставляет intent для повтора.

## Проверка

`python3 -m unittest pilot.test_pilot.MergeConflictRecoveryTests`

## Область

Реализация и тесты ограничены `pilot/pilot.py` и `pilot/test_pilot.py`; UI,
control-plane API, миграции и release broker вне области.

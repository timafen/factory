# Спецификация: terminal handoff после денежной паузы

## Цель и влияние на владельца

Устранить потерю следующего этапа, когда успешный терминальный этап попадает под денежную паузу. Пока лимит действует, новый этап не создаётся; после снятия паузы Factory автоматически продолжает текущее поколение ровно один раз. Владелец не должен вручную переотправлять работу и не должен получать дубликаты.

## Технический подход и реальные файлы

- `pilot/pilot.py`: изменить классификацию terminal handoff в `cycle()`: активная `stopped_pipelines` должна быть отложенным результатом, а не окончательной записью в `processed`; сохранить ID в retry/pinned-механизме до resume. После снятия паузы повторный проход должен пройти через обычный lifecycle/dedup guard и создать continuation атомарным request key.
- `pilot/pilot.py`: сохранить проверку `work_lifecycle_block()` по `work_id` Plan-root, чтобы старое поколение не возобновлялось; не менять денежные лимиты, правила очистки пауз и watchdog timeout.
- `pilot/test_pilot.py`: добавить регрессионный тест в `AdaptivePollingTests`, моделирующий денежную паузу, terminal result, следующий цикл при паузе и цикл после resume; проверить отсутствие создания, пригодность ID к повтору, ровно один continuation и отсечение старого `work_id`.

## Последовательный план

1. Определить в тестовом fixture stages, terminal task, активный Plan-root `work_id`, денежный лимит и `stopped_pipelines` для того же base title.
2. Выполнить `cycle()` при паузе и проверить, что `create_child_task`/`create_task` не вызван, terminal ID отсутствует среди окончательно обработанных либо явно закреплён для повтора.
3. Снять паузу, повторить цикл с тем же поколением и проверить создание continuation следующего этапа.
4. Повторить обработку неизменённого terminal snapshot и проверить идемпотентность: второй continuation не создаётся.
5. Добавить вариант со старым `work_id` и убедиться, что `work_lifecycle_block()` отбрасывает его как старое поколение; прогнать целевой и полный набор `pilot.test_pilot`.

## Критерии приёмки

- Денежная пауза не создаёт следующий этап и не превращает terminal ID в безвозвратно обработанный.
- После resume тот же terminal result автоматически создаёт ровно один следующий этап текущего поколения.
- Повторный цикл, два Pilot или повторная доставка request key не создают дубль.
- `work_lifecycle_block()` по Plan-root `work_id` по-прежнему блокирует старое поколение.
- Обычные owner-паузы, дедупликация terminal handoff, cursor fairness и `pipeline_watch()` не регрессируют.

## Тест-план

- Новый сценарный unit-тест: money limit → terminal success → stopped cycle → resume cycle → one child.
- В том же тесте assertions на `state["processed"]`/`terminal_retry_ids`, вызовы создания и совпадение `work_id` у созданного ребёнка.
- Отдельный subcase на старое поколение, отсекаемый lifecycle guard.
- Полная проверка: `python3 -m unittest pilot.test_pilot`.

## Риски и решения

- Риск повторного создания при конкурентных Pilot: использовать существующий детерминированный continuation request key и финальную проверку живого snapshot.
- Риск возобновить старую работу: требовать тот же `work_id`, что у активного Plan-root, и оставить `work_lifecycle_block()` источником истины.
- Риск starvation из-за закреплённого terminal ID: оставить bounded scan, cursor и retry pin; retry не должен обходить лимит terminal handoff.
- Риск изменения поведения обычной паузы: ограничить изменение веткой terminal handoff, покрыть существующие pause/watchdog тесты.

## Карточка работы

Карточка: `knowledge/cards/CARD-0175-terminal-handoff-after-money-pause.md`.

ГОТОВО-КОГДА: файл `pilot/pilot.py`
ГОТОВО-КОГДА: файл `pilot/test_pilot.py`
ГОТОВО-КОГДА: команда `python3 -m unittest pilot.test_pilot.AdaptivePollingTests.test_terminal_handoff_after_money_pause_resume`

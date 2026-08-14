Implementation commit: fc8548f244fe1eb2a1c653c224de668844e2f1a3 — Pilot фиксирует конфликт слияния и возвращает ту же работу в Implement + Test

# CARD-0127 — Pilot возвращает конфликт слияния в Implement + Test

## Контракт

После content conflict при слиянии Pilot сохраняет durable `merge_intent` в
`phase=conflict`, не повторяет тот же merge и создаёт ровно одну correction
задачу на исходной delivery-ветке. Correction наследует родителя и получает
`correction_kind=merge_conflict_return`; затем работа снова обязана пройти
Review и Verify.

## Область

- `pilot/pilot.py`: recovery merge intent, child task, worker/repository
  маршрутизация и вызов в cycle.
- `pilot/test_pilot.py`: conflict, exactly-once, provenance и повтор цикла.

## Проверка

Целевой тест: `python3 -m unittest pilot.test_pilot.MergeConflictRecoveryTests`.
Карточка создана для текущей работы; общие журналы знаний не изменяются.

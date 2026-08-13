# Спецификация: legacy fallback и stale-cache fixture для Review

## Цель и влияние на владельца

Review должен fail-closed, если repository identity отсутствует или не может
быть преобразована в удалённый репозиторий. В таком случае владелец получает
`BLOCKED: review infrastructure`, а не ложный `REQUEST CHANGES` по данным
неавторитетного `branch_report`. Регрессионная fixture должна воспроизводить
устаревший cached `origin/main`, чтобы тест доказывал разницу между ошибочным
cached scope и точным scope по закреплённым SHA.

## Технический подход и реальные файлы

- `pilot/pilot.py:2549-2554` — сохранить единый валидатор repository identity;
  `review_gate` не должен превращать пустой результат `_remote_url()` в
  успешный snapshot. Вызов `branch_report` удалить из authoritative Review
  path либо оставить только для явно изолированного legacy caller, который
  сразу возвращает `BLOCKED` и не продолжает gate/cap-rescue.
- `pilot/pilot.py:2568-2637` — authoritative путь по-прежнему получает
  symbolic default branch remote, fetch-ит её и candidate в изолированный
  репозиторий, а решения принимает только по `base_sha...candidate_sha`.
  Любая ошибка identity, resolution или fetch должна иметь `state=blocked`.
- `pilot/pilot.py:2869-2990` — убрать synthetic `unavailable` SHA и
  `branch_report`-файлы из `review_gate`; заблокированный snapshot должен
  завершать Review до `REQUEST CHANGES`, `cap_rescues`, проверки пустого
  diff и автоматического rebuild. Legacy-вызовы с identity `repo` перевести
  на валидный URL либо проверять как BLOCKED.
- `pilot/test_pilot.py:479-535` — переставить fixture: сначала клонировать
  `observer` после публикации candidate, затем продвинуть remote `main` и не
  обновлять observer. Зафиксировать старый cached ref до вызова snapshot;
  observer остаётся на своей рабочей ветке и не переключается/не сбрасывается.
- `pilot/test_pilot.py:330-468,650-735,930-980` — заменить искусственные
  legacy identity `repo` в тестах Review на валидную identity либо добавить
  отдельные проверки fail-closed. Не переписывать CARD-0087 и CARD-0090.

## Последовательный план

1. В `review_gate` сделать невалидную identity инфраструктурной ошибкой и
   удалить подстановку `branch_report` в authoritative snapshot.
2. Проверить все legacy Gate/cap-rescue тестовые вызовы и мигрировать их на
   валидный `file://`/HTTPS identity или на ожидаемый `blocked` результат.
3. Перестроить `FreshDefaultBranchSnapshotTests` в порядке clone observer →
   publish candidate → advance remote main; сохранить cached main старым.
4. Добавить assertions на старый cached comparison scope и на точный pinned
   scope, SHA, `ahead_by`, `base_advanced` и неизменность observer HEAD.
5. Запустить целевые и полный Pilot-набор, проверить пробелы, затем передать
   реализацию в отдельной ветке без изменений старых карточек.

## Критерии приёмки

- `review_gate` никогда не подменяет failed authoritative snapshot результатом
  `branch_report` и не выдаёт synthetic `unavailable` snapshot как успешный.
- Отсутствующая/невалидная repository identity даёт `blocked` с
  `BLOCKED: review infrastructure`; `REQUEST CHANGES`, cap-rescue и cached
  comparison для такого вызова не выполняются.
- Каждый legacy Gate/cap-rescue тест использует валидную identity или явно
  проверяет BLOCKED; искусственный identity `repo` не маскирует успех.
- Fixture клонирует observer до продвижения remote `main`; cached ref старый,
  remote base новый, worker-owned branch не переключается и не сбрасывается.
- Тест явно показывает ошибочный scope cached comparison и точный scope
  `base_sha...candidate_sha` pinned snapshot, включая SHA и счётчики.
- CARD-0087 и CARD-0090 не изменены; scope поставки содержит только файлы
  реализации, тестов и эту карточку/спецификацию по правилам этапа.

## Тест-план

- `python3 -m unittest -q pilot.test_pilot.FreshDefaultBranchSnapshotTests`
  — stale-cache fixture, pinned scope, SHA и сохранение observer branch.
- Целевые тесты `review_gate`/legacy Gate/cap-rescue — BLOCKED без
  `REQUEST CHANGES`, без вызова `branch_report` как authoritative fallback.
- `python3 -m unittest -q pilot.test_pilot` — регрессия всего Pilot-модуля.
- `git diff --check` — проверка документации и реализации без пробельных ошибок.

## Риски и решения

- Старые записи с неполной identity могут перестать проходить Review:
  принять fail-closed поведение и дать оператору диагностическую причину;
  не обвинять код через REQUEST CHANGES.
- Изменение порядка fixture может оставить cached ref незаметно свежим:
  до вызова snapshot явно считать SHA observer и сравнить его с новым remote
  main, затем assert-ить оба scope.
- Legacy unit tests могут зависеть от `branch_report`: мигрировать только
  тестовые seam-вызовы, не возвращая fallback в production Review path.
- Переписывание соседних карточек создаёт конфликт и размывает поставку:
  CARD-0087 и CARD-0090 оставить неизменными.

## Карточка работы

`knowledge/cards/CARD-0105-review-snapshot-legacy-fallback-stale-cache.md`
зарезервирована отдельно для этой работы; номер проверен в свежем
`origin/main` и опубликованных ветках.

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл knowledge/cards/CARD-0105-review-snapshot-legacy-fallback-stale-cache.md
ГОТОВО-КОГДА: команда python3 -m unittest -q pilot.test_pilot.FreshDefaultBranchSnapshotTests

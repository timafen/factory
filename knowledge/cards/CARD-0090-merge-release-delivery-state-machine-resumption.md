# CARD-0090 — Возобновление спецификации машины состояний слияния и выпуска

Implementation commit: ffd6159dd9c636bd2ac713e57fd9c0bab55ef5ed — выпуск после слияния стал durable и идемпотентным.

## Статус

Specification prepared. Эта карточка относится только к возобновлённому этапу
описания и не заменяет историческую CARD-0084 с журналом реализации.

## Результат

- Спецификация: `knowledge/specs/merge-release-delivery-state-machine-resumption.md`.
- Определены durable фазы delivery generation, границы recovery, правила N/N+1
  и условие честного завершения владельцу.
- Зафиксирован обязательный целевой тест состояния:
  `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests`.

## Проверка

Номер CARD-0090 и путь проверены по свежему `origin/main` и опубликованным
веткам перед созданием; UI и исходники приложения этим этапом не изменяются.

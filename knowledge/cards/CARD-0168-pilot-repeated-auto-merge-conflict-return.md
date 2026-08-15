# CARD-0168 — повторный AUTO-MERGE-конфликт снова запускает исправление

Implementation commit: 3f20d9347cb3986fec729ad0a76a7b56b54346a3 — базовый механизм сохраняет AUTO-MERGE-конфликт и возвращает его в Implement; текущая спецификация расширяет этот контракт на каждое следующее поколение конфликта.

## HEAD

Status: Specified — ожидает Implement + Test.

Branch: `factory/d6e37c53-b2f-f30f71d1-7c4`.

What changed: определён поколенческий контракт — новый конфликт после нового
Verify/head создаёт новый `merge_conflict_return`, а exactly-once действует
только внутри одного conflict-intent.

Evidence: фактические `recover_merge_intents()`, `resume_merge_conflicts()` и
8 текущих `MergeConflictRecoveryTests` сверены; baseline завершился с кодом 0,
а обязательная новая регрессия двух последовательных конфликтов названа в
спецификации.

One next action: реализовать привязку возврата к текущему Verify/head и тест
`test_repeated_conflict_creates_new_repair_generation` из
`knowledge/specs/pilot-repeated-auto-merge-conflict-return.md`.

## LOG

### 2026-08-14 — Specification

Текущий Pilot надёжно журналирует один конфликт и не дублирует его возврат,
но целевой класс не проверяет полный второй круг. Спецификация разделяет
идемпотентность по поколениям `(verify_task_id, commit_sha)`: старый
`repairing` intent остаётся аудитом, новый `conflict` получает собственную
correction-задачу, а повтор одного поколения остаётся exactly-once.

Номер и путь карточки проверены по свежему `origin/main` и опубликованным refs;
CARD-0168 до этой работы не занят.

## Ограничения

- Specification не меняет `pilot/pilot.py`, тесты, UI, API или конфигурацию;
  поставляются только этот документ и отдельная спецификация.
- Возврат сохраняет тот же `work_id`, repository и delivery-ветку; новый
  корень, Triage и Specification не создаются.
- Любая временная ошибка оставляет текущий conflict-intent повторяемым, но не
  разрешает снова вызывать merge для неизменённого head.

## Проверки для следующих этапов

- Два последовательных Verify/conflict создают `repair-1` и `repair-2` с
  разными parent/request key, но одной work/repository/branch.
- Повторный цикл и рестарт второго поколения не создают `repair-3`.
- Обязательная команда:
  `python3 -m unittest -q pilot.test_pilot.MergeConflictRecoveryTests.test_repeated_conflict_creates_new_repair_generation`.

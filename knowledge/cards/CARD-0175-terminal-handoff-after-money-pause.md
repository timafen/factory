# CARD-0175: terminal handoff после денежной паузы

Implementation commit: 830966200084178b2e4fb016c1236687fc548aa5 — текущая реализация terminal handoff и пауз, для которой специфицируется исправление

## Контекст

При денежном лимите terminal task может попасть в `stopped_pipelines`. Сейчас его ID фиксируется в `processed` до поздней проверки паузы; после resume текущего поколения handoff уже не рассматривается.

## Ожидаемое поведение

Во время паузы Factory не создаёт следующий этап и сохраняет terminal result пригодным к повтору. После снятия паузы создаётся ровно один continuation текущего Plan-root поколения. Старое поколение по иному `work_id` блокируется.

## Объём реализации

- `pilot/pilot.py`: исправить lifecycle terminal handoff и сохранение retry/pinned cursor с сохранением дедупликации и watchdog semantics.
- `pilot/test_pilot.py`: добавить сценарную регрессию money pause/resume и проверки generation guard.

## Проверка

Целевая команда и полный набор указаны в спецификации; реализация не входит в текущий этап Specification.

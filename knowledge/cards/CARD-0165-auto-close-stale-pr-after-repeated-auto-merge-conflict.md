# CARD-0165 — закрывать устаревший PR после повторного AUTO-MERGE-конфликта

Implementation commit: fc8548f244fe1eb2a1c653c224de668844e2f1a3 — базовый возврат AUTO-MERGE-конфликта в Implement, на котором строится текущая спецификация.

## HEAD

Status: Specified — ожидает Implement + Test.
Branch: `factory/a1f7282a-658-b45d5be6-f0a`.
What changed: определён fail-closed контракт: после второго конфликта Pilot
закрывает только свой открытый PR, если другой PR с тем же exact `work_id`
marker уже merged в ту же base branch; иначе сохраняется обычный repair flow.
Evidence: фактические `recover_merge_intents()`, `resume_merge_conflicts()` и
`MergeConflictRecoveryTests` сверены; целевой текущий класс — 4 теста, OK.
One next action: реализовать marker, conflict generation, GitHub lookup/close,
durable audit и регрессии из `knowledge/specs/auto-close-stale-pr-after-repeated-auto-merge-conflict.md`.

## LOG

### 2026-08-14 — Specification

Пилот уже журналирует первый conflict и возвращает работу в Implement, но
`merge_intent` не хранит машинную связь PR с одной работой и не умеет отличить
доставку через другой PR. Спецификация добавляет immutable `work_id` marker,
отдельную target branch, счётчик конфликтов, состояния `superseding` и
`superseded`, строгую проверку current/merged PR и безопасный повтор после
неясного ответа close. Номер и путь карточки проверены по свежему main и
опубликованным refs; занятые варианты не переиспользованы.

## Ограничения

- На Specification не меняются `pilot/pilot.py`, UI, control-plane, worker или
  конфигурация; поставляются только спецификация и эта карточка.
- Кандидат для auto-close обязан иметь exact marker и exact base; title,
  branch, похожий текст и PR без marker не являются доказательством.
- При любой ошибке GitHub, неоднозначном списке PR или отсутствии immutable
  `work_id` PR не закрывается, а текущий correction flow остаётся доступным.

## Проверки для следующих этапов

- Позитивный второй conflict: один close, terminal `superseded`, audit merged
  PR и отсутствие correction task.
- Первый conflict, legacy intent, другой `work_id`, human PR, другая base,
  malformed marker и GitHub error: close отсутствует, repair flow сохранён.
- Restart после `superseding`/`superseded`: нет повторного close/comment/task.
- Обязательная команда: `python3 -m unittest -q pilot.test_pilot.MergeConflictRecoveryTests`.

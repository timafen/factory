# CARD-0101 — «Сделано недавно»: влитое отдельно и даты по-человечески

## HEAD

- Status: Implemented; целевые проверки проходят, общий UI-gate содержит внешнюю находку.
- Branch: `factory/6e733444-f48c-5bb32b39-e7c`.
- Implementation commit: 0ec03a13e90f3e57ef46817d142c72135867f924 — раздельные группы влитого и провалов с человекочитаемыми датами.
- What changed: delivery receipt подтверждает только влитое; `failed` и `cancelled` получают отдельные этап и причину, с независимыми лимитами и дедупликацией.
- What changed: «Обзор» показывает две секции, локальные даты, «Влито в main» и честную подпись очереди.
- Evidence: целевой Python-контракт — 1/1; `RecentDoneTest` — 6/6; `Overview.test.ts` — 22/22; lint и `py_compile` — PASS.
- Evidence: `typecheck` и `build` остановлены на существующей ошибке `web/e2e/control-plane.spec.ts:655` вне области этой работы.
- Evidence: единичный `just check` прошёл `vet` и `govulncheck`, но остановлен прежним `SA4000` в `internal/worker/attempt_lifecycle_test.go:31` вне области.
- One next action: после общего gate открыть `/` и проверить блок «Сделано недавно» на стенде.

## LOG

### 2026-08-12 — Specification

Контракт dashboard и точки изменений зафиксированы для реализации спецификации.

#### Что сделать

- Разделить на «Обзоре» подтверждённые слияния и провалы с независимыми лимитами.
- Показывать у провала этап и доступную причину, не выдавая его за влитую работу.
- Форматировать даты локально как сегодня, вчера или понятную старую дату;
  невалидное и пустое значение обозначать явно.
- Переписать подпись очереди без «замер» и `p90`, сохранив «данных нет».

#### Область

`pilot/pilot.py`, `pilot/test_pilot.py`, `web/src/Overview.tsx`,
`web/src/Overview.test.ts`.

#### Проверка

`python3 -m unittest -v pilot.test_pilot.RecentDoneTest.test_separates_merged_and_failed_with_independent_limits`

#### Связь со спецификацией

`knowledge/specs/recent-done-merged-failures-human-dates.md`

### 2026-08-12 — Implement

Dashboard теперь возвращает независимые группы `merged` и `failed`: receipt
подтверждает влитие, провалы показывают этап и последнюю доступную причину,
а старые уведомления остаются только аудитом. Обзор форматирует даты локально,
разделяет секции и использует человеческую подпись очереди.

Проверки: целевой Python-контракт 1/1, `RecentDoneTest` 6/6, `Overview.test.ts`
22/22, lint и `py_compile` прошли; общий typecheck/build зафиксирован как
НАХОДКА в существующем `web/e2e/control-plane.spec.ts:655`, а `just check` —
на существующем `internal/worker/attempt_lifecycle_test.go:31`; оба вне области.

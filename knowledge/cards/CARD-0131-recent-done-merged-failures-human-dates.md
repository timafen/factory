# CARD-0131 — «Сделано недавно»: влитое отдельно и даты по-человечески

Implementation commit: 92249bc3b72e20194da28e69eaba5376d0317e60 — подтверждённые слияния и остановки разделены, даты и причины понятны владельцу.

## HEAD

- Status: Implemented.
- Branch: `factory/6aa68573-b76-af079407-090`.
- Implementation commit: 92249bc3b72e20194da28e69eaba5376d0317e60 — подтверждённые слияния и остановки разделены, даты и причины понятны владельцу.
- What changed: dashboard выдаёт независимые группы `merged` и `failed`; receipt остаётся единственным доказательством влития.
- What changed: обзор показывает «Влито» и «Остановилось», локальные даты, этап и причину без ID, статусов и ISO-фрагментов.
- Evidence: `python3 -m unittest -v pilot.test_pilot.RecentDoneTest` → 6 tests OK.
- Evidence: `npm --prefix web test -- --run src/Overview.test.ts` → 30 tests passed; typecheck and build passed.
- Next action: повторно запустить Review для опубликованной ветки-кандидата.

## LOG

### 2026-08-13 — Implement

Серверный контракт разделён на подтверждённые receipt-слияния и `failed`/`cancelled`
остановки с независимым лимитом пяти записей. Интерфейс показывает человеческие
даты, этап и причину, а контрактная и UI-регрессии подтверждают, что пять новых
провалов не скрывают четыре влитые работы.

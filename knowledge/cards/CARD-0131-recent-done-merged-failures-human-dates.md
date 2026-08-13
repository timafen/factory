# CARD-0131 — «Сделано недавно»: влитое отдельно и даты по-человечески

Implementation commit: e63687448b95dbfbb0f6d9649cea7caf51e02172 — подтверждённые слияния и остановки разделены, даты и причины понятны владельцу.

## HEAD

- Status: Implemented.
- Branch: `factory/1172f160-a6b-becf7b8a-6a3`.
- Implementation commit: e63687448b95dbfbb0f6d9649cea7caf51e02172 — подтверждённые слияния и остановки разделены, даты и причины понятны владельцу.
- What changed: dashboard выдаёт независимые группы `merged` и `failed`; receipt остаётся единственным доказательством влития.
- What changed: обзор показывает «Влито» и «Остановилось», локальные даты, этап и причину без ID, статусов и ISO-фрагментов.
- Evidence: `python3 -m unittest -v pilot.test_pilot.RecentDoneTest` → 6 tests OK.
- Evidence: `npm --prefix web test -- --run src/Overview.test.ts` → 30 tests passed; typecheck and build passed.
- Next action: проверить результат на странице обзора после поступления свежего dashboard-снимка.

## LOG

### 2026-08-13 — Implement

Серверный контракт разделён на подтверждённые receipt-слияния и `failed`/`cancelled`
остановки с независимым лимитом пяти записей. Интерфейс показывает человеческие
даты, этап и причину, а контрактная и UI-регрессии подтверждают, что пять новых
провалов не скрывают четыре влитые работы.

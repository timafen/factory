Implementation commit: 58d937492487b9e92c06155ec28d6151214a5f65 — строгая проверка дат, независимые лимиты групп и честный значок провалов в исходной работе.

# CARD-0101 — «Сделано недавно»: влитое отдельно и даты по-человечески

## HEAD

- Status: Specification; исходная работа определена, повтор закрыт.
- Owner decision: запись-дубликат не развивать; продолжать только CARD-0101.
- Scope: `pilot/pilot.py`, `pilot/test_pilot.py`, `web/src/Overview.tsx`,
  `web/src/Overview.test.ts`.
- Acceptance: влитое и провалы имеют независимые лимиты; даты и подписи понятны
  человеку; провалы не получают зелёный знак готовности.
- Required check: `python3 -m unittest -v pilot.test_pilot.RecentDoneTest.test_separates_merged_and_failed_with_independent_limits`.
- Specification: `knowledge/specs/recent-done-merged-failures-human-dates.md`.

## LOG

### 2026-08-13 — Specification

Повтор закрыт по решению владельца. Проверяемый контракт перенесён в исходную
CARD-0101: receipt остаётся единственным доказательством слияния, подтверждённые
слияния и провалы получают независимые лимиты, а интерфейс показывает локальные
даты, этап и причину без машинных статусов и голых идентификаторов.

Перед выпуском исходную реализацию нужно перенести на свежий `origin/main` и
выполнить обязательные серверные и UI-проверки, включая установку зависимостей,
TypeScript typecheck и Vitest.

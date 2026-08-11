# CARD-0059 — «Сделано недавно» показывает конечные результаты

Implementation commit: 0cefeef2528f4d7227ee5037bb860d202b5d35ec — успешные этапы без подтверждённого слияния исключены из завершённых работ.

## HEAD

- Status: Implemented — ожидает проверки и слияния.
- Branch: `factory/18f6e7d1-baf-6ca161f3-f25`.
- Implementation commit: 0cefeef2528f4d7227ee5037bb860d202b5d35ec — блок оставляет только подтверждённые слияния и конечные ошибки.
- What changed: успешные промежуточные этапы и Verify без записи merge больше
  не попадают в «Сделано недавно»; подтверждённые слияния и terminal failures
  остаются видимыми.
- Evidence: обязательная регрессия — 1 test OK; весь `RecentDoneTest` — 5 tests
  OK; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` и `just build` — OK.
- One next action: повторно проверить изменение на стадии Review.

## LOG

### 2026-08-10 — Implement

«Сделано недавно» больше не выдаёт продвижение pipeline за завершённую работу:
успешный Triage и успешный Verify без записи в merge-журнале исключаются.
Регрессия одновременно фиксирует сохранение подтверждённого слияния и конечной
ошибки Review.

Проверки: `python3 -m unittest pilot.test_pilot.RecentDoneTest -v` — 4 tests
OK; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py`, `just build` и
`git diff --check` — OK.

### 2026-08-10 — Implement

Работа пересобрана от свежего `origin/main`. Добавлен отдельный обязательный тест
`RecentDoneTest.test_ignores_succeeded_intermediate_triage`: успешный Triage без
записи о merge не отображается как завершённая работа.

Проверки: обязательная регрессия — 1 test OK; весь `RecentDoneTest` — 5 tests
OK; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py`, `just build` и
`git diff --check` — OK.

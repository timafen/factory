# CARD-0059 — «Сделано недавно» показывает конечные результаты

Implementation commit: 3477885e34dc3b015f05ac208e5f88ba0f37eb0f — успешные этапы без подтверждённого слияния исключены из завершённых работ.

## HEAD

- Status: Implemented — ожидает проверки и слияния.
- Branch: `factory/2b2f3b09-a32-2ea2022a-70c`.
- Implementation commit: 3477885e34dc3b015f05ac208e5f88ba0f37eb0f — блок оставляет только подтверждённые слияния и конечные ошибки.
- What changed: успешные промежуточные этапы и Verify без записи merge больше
  не попадают в «Сделано недавно»; подтверждённые слияния и terminal failures
  остаются видимыми.
- Evidence: `python3 -m unittest pilot.test_pilot.RecentDoneTest -v` — 4 tests
  OK; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` и `just build` — OK.
- One next action: проверить критерии CARD-0059 на стадии Verify.

## LOG

### 2026-08-10 — Implement

«Сделано недавно» больше не выдаёт продвижение pipeline за завершённую работу:
успешный Triage и успешный Verify без записи в merge-журнале исключаются.
Регрессия одновременно фиксирует сохранение подтверждённого слияния и конечной
ошибки Review.

Проверки: `python3 -m unittest pilot.test_pilot.RecentDoneTest -v` — 4 tests
OK; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py`, `just build` и
`git diff --check` — OK.

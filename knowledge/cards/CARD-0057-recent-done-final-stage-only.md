# CARD-0057 — «Сделано недавно» показывает только завершённые работы

Implementation commit: 02622ae226c41f52ff2d69d1599795c91b0be3b3 — успешная промежуточная стадия исключена из завершённых работ.

## HEAD

- Status: Implemented — ожидает проверки и слияния.
- Branch: `factory/0ae45807-584-df9dbc25-b46`.
- Implementation commit: 02622ae226c41f52ff2d69d1599795c91b0be3b3 — успешная промежуточная стадия исключена из завершённых работ.
- What changed: блок «Сделано недавно» пропускает успешные стадии до финальной;
  финал одноэтапного конвейера остаётся видимым.
- Evidence: `python3 -m unittest pilot.test_pilot.RecentDoneTest -v` — 4 tests OK;
  `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` и `just build` — OK.
- One next action: проверить блок «Сделано недавно» на данных конвейера после слияния.

## LOG

### 2026-08-10 — Implement

Успешный промежуточный `Triage` больше не выдаётся владельцу за завершённую
работу. Целевой тест одновременно подтверждает, что финальный `Triage` в
одноэтапном конвейере остаётся результатом.

Проверки: `python3 -m unittest pilot.test_pilot.RecentDoneTest -v` — 4 tests
OK; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py`, `just build` и
`git diff --check` — OK.

# CARD-0057 — «Сделано недавно» показывает только завершённые работы

Implementation commit: 27c3dc36f8e7cab408a10d2860cc7bf232828f86 — обязательная проверка промежуточного Triage закреплена точным именем.

## HEAD

- Status: Implemented — замечание ревью исправлено, ожидает повторной проверки.
- Branch: `factory/d4b87617-476-bd286c9c-2a6`.
- Implementation commit: 27c3dc36f8e7cab408a10d2860cc7bf232828f86 — обязательная проверка промежуточного Triage закреплена точным именем.
- What changed: блок «Сделано недавно» пропускает успешные стадии до финальной;
  финал одноэтапного конвейера остаётся видимым, а обязательный тест доступен
  под согласованным именем.
- Evidence: обязательный точечный `unittest` — 1 test OK; весь
  `pilot.test_pilot.RecentDoneTest` — 4 tests OK; `py_compile` и `just build` — OK.
- One next action: повторно проверить и слить ветку.

## LOG

### 2026-08-10 — Implement

Успешный промежуточный `Triage` больше не выдаётся владельцу за завершённую
работу. Целевой тест одновременно подтверждает, что финальный `Triage` в
одноэтапном конвейере остаётся результатом.

Проверки: `python3 -m unittest pilot.test_pilot.RecentDoneTest -v` — 4 tests
OK; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py`, `just build` и
`git diff --check` — OK.

### 2026-08-10 — Implement

Устранён блокер ревью: тест сценария теперь называется
`test_ignores_succeeded_intermediate_triage`, как требует приёмка, без изменения
подтверждённого поведения. Точная обязательная команда — 1 test OK; весь класс —
4 tests OK; `py_compile` и `just build` — OK.

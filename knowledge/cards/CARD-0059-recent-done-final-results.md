# CARD-0059 — «Сделано недавно» показывает только завершённую работу

Implementation commit: 100ecec6cdb4c6bcda4e0615959e63662e7ff26a — успешные промежуточные этапы исключены из «Сделано недавно».

## HEAD

- Status: Implemented — awaiting Verify.
- Branch: `factory/713cf42c-248-9ea02867-e59`.
- Implementation commit: 100ecec6cdb4c6bcda4e0615959e63662e7ff26a — успешный этап отображается только после подтверждённого слияния.
- What changed: успешный Triage и неподтверждённый Verify больше не считаются завершённой работой.
- What changed: подтверждённые слияния, конечные ошибки и отмены сохраняют прежнее поведение.
- Evidence: `python3 -m unittest pilot.test_pilot.RecentDoneTest` → 5 tests OK.
- Evidence: `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` → успешно; `just build` → оба бинарника собраны.
- One next action: выполнить стадию Verify на опубликованной ветке.

## LOG

### 2026-08-10 — Implement

Блок «Сделано недавно» теперь опирается на журнал слияний для успешных результатов и не выдаёт промежуточный Triage за законченную работу. Целевые пять сценариев прошли; проект собран без ошибок.

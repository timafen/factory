Implementation commit: 3e07dad0de5087da956b7a310e44e3dcb42151a8 — Pilot закрывает устаревший PR только по точному work_id уже влитой работы

# CARD-0165: закрывать устаревший PR уже влитой работы

## HEAD

Status: Implemented and tested — awaiting Review
Branch: factory/da49cc79-c32-aedfea1f-ec8
Implementation commit: `3e07dad0de5087da956b7a310e44e3dcb42151a8` — в PR добавлен
неизменяемый marker, а повторный AUTO-MERGE-конфликт безопасно распознаёт уже
влитую работу в той же целевой ветке.
What changed: Pilot закрывает и комментирует только свой открытый устаревший PR
с точным `work_id`; несовпадения и ошибки GitHub оставляют обычный repair flow.
Evidence: обязательный тест закрытия дубликата → 1 test, OK; полный
`python3 -m unittest -q pilot.test_pilot` → 346 tests, OK (13 skipped);
`npm --prefix web run build` → production build completed.
One next action: Review проверить строгую идентичность marker и возобновление
закрытия после сбоя GitHub без повторного close/comment/task.

## LOG

### 2026-08-15 — Implement

В `pilot/pilot.py` durable `work_id` сохраняется в merge intent и публикуется
ровно одним машинным marker. После второго конфликта Pilot сверяет открытый PR
и merged PR той же base branch, durably фиксирует решение, закрывает только
устаревший PR и оставляет audit evidence. В `pilot/test_pilot.py` подтверждены
positive flow, идемпотентность, fail-closed ошибки и отрицательные варианты
без marker, с иным marker, двойным marker, human PR и другой base branch.

Implementation commit: 3d4a15f2d9e74a6f5e88c22ef2f3fa0a5c63dc86 — Pilot закрывает устаревший PR уже после первого AUTO-MERGE-конфликта

# CARD-0165: закрывать устаревший PR уже влитой работы

## HEAD

Status: Implemented and tested — awaiting Review
Branch: factory/b9871961-9c1-7fb37fa7-002
Implementation commit: `3d4a15f2d9e74a6f5e88c22ef2f3fa0a5c63dc86` — проверка уже
влитого PR запускается при первом AUTO-MERGE-конфликте.
What changed: Pilot закрывает и комментирует только свой открытый устаревший PR
с точным `work_id`, включая `rounds=1`; несовпадения и ошибки GitHub оставляют
обычный repair flow.
Evidence: `python3 -m unittest -v pilot.test_pilot.MergeConflictRecoveryTests`
→ 12 tests, OK; `git diff --check` → OK.
One next action: Review проверить первый конфликт, идемпотентность закрытия и
комментария без создания repair-задачи.

## LOG

### 2026-08-15 — Implement

В `pilot/pilot.py` durable `work_id` сохраняется в merge intent и публикуется
ровно одним машинным marker. После второго конфликта Pilot сверяет открытый PR
и merged PR той же base branch, durably фиксирует решение, закрывает только
устаревший PR и оставляет audit evidence. В `pilot/test_pilot.py` подтверждены
positive flow, идемпотентность, fail-closed ошибки и отрицательные варианты
без marker, с иным marker, двойным marker, human PR и другой base branch.

### 2026-08-15 — Implement

Убрано ограничение `rounds >= 2`: уже при первом AUTO-MERGE-конфликте Pilot
ищет влитый PR с тем же точным `work_id`, закрывает устаревший PR и не создаёт
repair-задачу. Целевой `MergeConflictRecoveryTests` прошёл: 12 tests, OK;
`git diff --check` прошёл.

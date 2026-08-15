Implementation commit: ecdac4dbc0dce2ead042ba974e3c525874d2acb1 — Pilot закрывает устаревший PR уже после первого AUTO-MERGE-конфликта

# CARD-0165: закрывать устаревший PR уже влитой работы

## HEAD

Status: Implemented and tested — awaiting Review
Branch: factory/5db83753-34d-2d34f8db-65e
Implementation commit: `ecdac4dbc0dce2ead042ba974e3c525874d2acb1` — проверка уже
влитого PR запускается при первом AUTO-MERGE-конфликте.
What changed: Pilot закрывает и комментирует только свой открытый устаревший PR
с точным `work_id`, включая `rounds=1`; несовпадения и ошибки GitHub оставляют
обычный repair flow.
Evidence: `python3 -m unittest -v pilot.test_pilot.MergeConflictRecoveryTests`
→ 10 tests, OK; `python3 -m unittest pilot.test_pilot` → 351 tests, OK
(13 skipped); `git diff --check` → OK.
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

### 2026-08-15 — Implement

После rebase на свежий `main` сохранена безопасная проверка точного `work_id`,
а условие второго конфликта снято: stale PR закрывается уже после первого.
`python3 -m unittest -v pilot.test_pilot.MergeConflictRecoveryTests` — 10 OK;
`python3 -m unittest pilot.test_pilot` — 351 OK, 13 skipped.

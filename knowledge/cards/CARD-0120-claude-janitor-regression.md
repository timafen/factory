Implementation commit: 8dfe8b32f453d2e94e385cb59d812e04ddd8a0ad — регрессия доказывает пропуск online/unhealthy Claude с retained worktree.

# CARD-0120 — доказательство границы CARD-0093

## HEAD

- Status: Implemented — targeted checks PASS, awaiting Verify
- Branch: `factory/98cc60eb-656-58a8ebd5-4b9`
- Implementation commit: 8dfe8b32f453d2e94e385cb59d812e04ddd8a0ad — тест санитаря моделирует online/unhealthy Claude с retained worktree.
- What changed: fixture теперь исключает обход проверки из-за пустого `retained_worktrees`; отсутствие stop/start, карантина и новой записи в state проверяется для реально подходящего по остальным условиям worker.
- Scope boundary: CARD-0093 остаётся защитой санитаря; первопричина ложного `unhealthy` и ожидание занятого health-probe принадлежат CARD-0098.
- Evidence: `bash ops/test-factory-janitor.sh` → 4 PASS; `bash -n ops/factory-janitor.sh ops/test-factory-janitor.sh` → PASS; `git diff --check` → PASS.
- One next action: Verify выполнить целевой тест санитаря на опубликованном HEAD.

## LOG

### 2026-08-13 — Implement

Усилен сценарий online/unhealthy: API возвращает удержанный worktree, поэтому
удаление проверки `online` теперь вызовет регрессию. Санитар не делает stop/start,
не переносит результат в карантин и не резервирует попытку для живого worker;
четыре целевых сценария и синтаксическая проверка прошли.

Implementation commit: 8dfe8b32f453d2e94e385cb59d812e04ddd8a0ad — регрессия доказывает пропуск online/unhealthy Claude с retained worktree.

# CARD-0120 — доказательство границы CARD-0093

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/98cc60eb-656-58a8ebd5-4b9`
- Implementation commit: 8dfe8b32f453d2e94e385cb59d812e04ddd8a0ad — тест санитаря моделирует online/unhealthy Claude с retained worktree.
- What changed: fixture теперь исключает обход проверки из-за пустого `retained_worktrees`; отсутствие stop/start, карантина и новой записи в state проверяется для реально подходящего по остальным условиям worker.
- Scope boundary: CARD-0093 остаётся защитой санитаря; первопричина ложного `unhealthy` и ожидание занятого health-probe принадлежат CARD-0098.
- Evidence: `bash ops/test-factory-janitor.sh` → 4 PASS; `just build` → PASS; `just test-release` → PASS. `just check` дошёл до `staticcheck` и выявил существующую SA4000 вне области поставки.
- One next action: Человеку выполнить merge после учёта известного долга staticcheck.

## LOG

### 2026-08-13 — Implement

Усилен сценарий online/unhealthy: API возвращает удержанный worktree, поэтому
удаление проверки `online` теперь вызовет регрессию. Санитар не делает stop/start,
не переносит результат в карантин и не резервирует попытку для живого worker;
четыре целевых сценария и синтаксическая проверка прошли.

### 2026-08-13 — Verify

| Критерий | Команда/проверка | Наблюдение |
| --- | --- | --- |
| Живой `online/unhealthy` с retained worktree не перезапускается | `bash ops/test-factory-janitor.sh` | `TestJanitorSkipsOnlineUnhealthyWorker: PASS`; нет `stop/start` в логе `systemctl`. |
| Такой worker не попадает в карантин | тот же сценарий | retained worktree остаётся, quarantine-файл не создан. |
| Такому worker не резервируется новая попытка | тот же сценарий | `online-unhealthy` отсутствует в `heals.json`. |
| Офлайн-worker с retained worktree по-прежнему обрабатывается | тот же сценарий | очистка, карантин и подтверждение API проходят; все 4 сценария PASS. |
| Сборка и выпуск не регрессировали | `just build`; `just test-release` | PASS; release-артефакты воспроизводимы. |
| Полный обычный набор | `npm --prefix web ci`; `just check` | UI-зависимости PASS; `just check` остановился на прежнем `SA4000` в `internal/worker/attempt_lifecycle_test.go:31`, вне изменённых файлов. |
| Браузерный набор | `just test-browser` | 5 PASS, 1 FAIL в несвязанном `web/e2e/control-plane.spec.ts:833` (`renders grouped work and saves the desktop Work view`); 15 тестов после него не запущены. |

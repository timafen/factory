# CARD-0052 — Сторож застрявших конвейеров снова работает в цикле Пилота

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/3491f202-e2f-39c55d92-ab7`.
- Head commit: `e488055` (проверенный снимок возврата сторожа в цикл).
- What changed: `cycle()` снова вызывает `pipeline_watch` после ответов владельца
  и перед обработкой завершённых этапов; сторож использует тот же актуальный снимок.
- Evidence: `python3 -m unittest pilot.test_pilot` → 103 tests OK;
  `just ui-check` → OK; `just test` → OK.
- One next action: влить проверенную поставку в `main`.

## LOG

### 2026-08-10 — Implement

Вызов сторожа был исключён при переносе отдельного патруля в Automations,
хотя автономное восстановление потерянного перехода всё ещё принадлежит Пилоту.
`cycle()` снова передаёт сторожу текущие задачи, workflows и workers после
обработки ответов владельца. Тесты подтверждают вызов в обычном и перегруженном
цикле; 103 проверки Пилота и TypeScript-проверка web прошли.

### 2026-08-10 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Сторож вызывается в обычном цикле с актуальным снимком | `python3 -m unittest pilot.test_pilot` | `test_cycle_runs_pipeline_watch_with_current_snapshot` прошёл: переданы текущие задачи, workflows и workers. |
| Сторож работает и при перегрузке хоста | `python3 -m unittest pilot.test_pilot` | `test_overload_does_not_stop_cycle_services` прошёл: вызов выполнен с пустым актуальным снимком. |
| Изменение не ломает смежное поведение Пилота | `python3 -m unittest pilot.test_pilot` | 103 проверки прошли. |
| Основные проверки проекта | `just test`; `just ui-check` | Обе команды прошли. |

`just check` остановился на существующих предупреждениях `staticcheck` вне области
поставки: неиспользуемое поле в `internal/controlplane/cards_http.go` и значение
`err` в `internal/controlplane/pilot_config.go`. Это долг проекта, не регрессия
сторожа: целевые и затронутые проверки прошли.

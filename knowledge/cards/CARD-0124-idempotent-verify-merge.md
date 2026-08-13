# CARD-0047 — Идемпотентный финал Verify

## HEAD

- Status: Implemented — ожидает проверки и слияния.
- Branch: `factory/3537760b-0da-4ef48574-8b9`.
- Implementation commit: e749e7b2ccfe04b721600a3603c0a6d9e5e10326 — обзор показывает реальные работы.
- What changed: «Сделано недавно» строится из задач конвейера и журнала merge;
  служебные smoke/helper/debug/idempotency финалы не вытесняют работы владельца.
  Verify без подтверждённого merge не названа влитой, а реальный провал виден явно.
- Evidence: `python3 -m unittest pilot.test_pilot` — 154 OK; `npm test -- --run src/Overview.test.ts` — 13 OK; build/lint/typecheck — OK.
- One next action: открыть обзор и проверить блок «Сделано недавно» на живых данных.

## LOG

### 2026-08-10 — Implement

Экран недавних работ получил источник из фактической истории pipeline с
пагинацией, понятным доказательством и временем. Пять разновидностей
служебных финалов исключаются; две реальные работы, включая несостоявшийся
финал, остаются видимыми. Слияние подтверждается только записью merge-журнала.

Проверки: `python3 -m unittest pilot.test_pilot` — 154 OK; `cd web && npm test
-- --run src/Overview.test.ts` — 13 OK; `npm run typecheck`, `npm run lint` и
`npm run build` — OK.

### 2026-08-10 — Implement

Добавлена устойчивая отметка завершённого мёржа по ID Verify-задачи. Она
переживает потерю временного курсора при рестарте и исключает повторный мёрж
либо вторую строку на экране обзора. Новый целевой тест запускает один PASS
дважды как после рестарта и подтверждает единственность мёржа и записи.

Проверки: `python3 -m unittest pilot.test_pilot.PipelineWatchTests` — 8/8 OK;
`python3 -m py_compile pilot/pilot.py` и `git diff --check` — OK.

### 2026-08-10 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Повторный Verify PASS не создаёт второй мёрж | `PipelineWatchTests.test_verify_pass_is_processed_once` в полном наборе | `gh_merge` вызван один раз после двух циклов |
| Повторный Verify PASS не создаёт вторую запись | тот же сценарий с временным журналом мёржей | в журнале одна запись с ID Verify-задачи |
| Изменение не ломает соседние сценарии оркестратора | `python3 -m unittest pilot.test_pilot -v` | 88 тестов прошли за 47,346 с |

Дополнительно: `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` и
`git diff --check origin/main...HEAD` — OK. Ветка перебазирована на актуальный
`origin/main`; рабочее дерево перед записью карточки было чистым.

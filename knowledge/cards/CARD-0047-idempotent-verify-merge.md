# CARD-0047 — Идемпотентный финал Verify

## HEAD

- Status: Verified PASS — ожидает решения человека о мёрже.
- Branch: `factory/6c75a321-d8f-63bda207-a1b`.
- Head commit: `7bb0686` (`Зафиксировать защиту финала Verify в карточке`).
- What changed: журнал мёржей хранит ID финальной Verify-задачи; повторная
  обработка этого PASS пропускает финализацию, мёрж и новую запись в журнале.
- Evidence: полный набор `python3 -m unittest pilot.test_pilot -v` — 88/88 OK;
  сценарий повторной обработки Verify PASS подтверждает ровно один мёрж и одну запись.
- One next action: человеку проверить и влить доставленную ветку.

## LOG

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

# CARD-0047 — Автопочинка не считает один запуск дважды

## HEAD

- Status: Verified PASS — ожидает вливания человеком.
- Branch: `factory/2818329c-8c0-11073b0a-2cf`.
- Head commit: `0728cc2` (`Зафиксировать проверку двойного учёта автопочинки`).
- Specification: `knowledge/specs/diag-repair-duplicate-active-runs.md`.
- What changed: полный список активных задач объединяется по непустому ID;
  повтор кандидата больше не блокирует адресную автопочинку.
- Evidence: полный набор `pilot.test_pilot` → 87/87 OK; `DiagnosisRepairTests`
  → 17/17 OK; `py_compile` и `git diff --check` → OK.
- One next action: человеку влить проверенную ветку в `main`.

## LOG

### 2026-08-10 — Implement

Исправлен двойной учёт одного активного запуска, повторённого API: одинаковый
непустой ID учитывается один раз, а разные ID и записи без ID остаются отдельными.
Регрессионный сквозной сценарий подтверждает одну отмену и одно продолжение;
все 17 сценариев автопочинки, компиляция Python и проверка diff прошли.

### 2026-08-10 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Повтор одного ID отменяется и продолжается один раз | `test_duplicate_active_id_is_cancelled_once_then_resumed_same_branch` | одна отмена, после терминального состояния одно продолжение на прежней ветке |
| Разные ID не разрешают отмену, включая вторую страницу | `test_ambiguous_active_runs_are_not_cancelled`; `test_active_run_beyond_first_page_prevents_any_cancellation` | сохранён отказ «найдено активных запусков — 2», адресная отмена не вызвана |
| Все сценарии автопочинки проходят | `python3 -m unittest pilot.test_pilot.DiagnosisRepairTests -v` | 17/17 OK |

Полный запуск `python3 -m unittest pilot.test_pilot -v` прошёл: 87/87 OK.
`python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` и `git diff --check`
прошли; рабочее дерево чистое.

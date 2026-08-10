# CARD-0047 — Идемпотентный финал Verify

## HEAD

- Status: Implemented — готово к Verify.
- Branch: `factory/6c75a321-d8f-63bda207-a1b`.
- Head commit: `a2742ed` (`Исключить повторный мёрж после Verify PASS`).
- What changed: журнал мёржей хранит ID финальной Verify-задачи; повторная
  обработка этого PASS пропускает финализацию, мёрж и новую запись в журнале.
- Evidence: `python3 -m unittest pilot.test_pilot.PipelineWatchTests` — 8/8 OK;
  новый сценарий имитирует рестарт и подтверждает ровно один мёрж и одну запись.
- One next action: выполнить этап Verify поставки.

## LOG

### 2026-08-10 — Implement

Добавлена устойчивая отметка завершённого мёржа по ID Verify-задачи. Она
переживает потерю временного курсора при рестарте и исключает повторный мёрж
либо вторую строку на экране обзора. Новый целевой тест запускает один PASS
дважды как после рестарта и подтверждает единственность мёржа и записи.

Проверки: `python3 -m unittest pilot.test_pilot.PipelineWatchTests` — 8/8 OK;
`python3 -m py_compile pilot/pilot.py` и `git diff --check` — OK.

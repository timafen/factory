Implementation commit: PENDING — этап Specification не меняет продуктовый код; заменить полным SHA реализации фильтра архивных попыток

# CARD-0161: архивные вытесненные попытки вне лимита повторов

## HEAD

Status: Specified — awaiting Implement + Test
Branch: factory/cab06c19-5e1-fe6a0a2d-e54
Specification: `knowledge/specs/archived-superseded-attempts-do-not-spend-retry-limit.md`
Owner outcome: сохранённые в истории вытесненные попытки не приближают текущую
работу к преждевременной остановке по `max_stage_attempts`.
Implementation scope: `pilot/pilot.py`, `pilot/test_pilot.py`.
Required check: `python3 -m unittest pilot.test_pilot.CorrectionProvenanceStormTests`.
One next action: реализовать фильтрацию `archived_attempts` в общем счётчике
`stage_attempts` и заменить `PENDING` выше полным SHA продуктового коммита.

## LOG

### 2026-08-14 — Specification

Фактическая причина локализована: архиватор уже сохраняет ID вытесненных задач
в `works.json.archived_attempts`, но `stage_attempts` считает все совпавшие
задачи и не читает архивную квитанцию. Определены точечное изменение Pilot,
защита от смешения одноимённых работ и обязательная регрессия без изменений UI,
API или схемы данных.

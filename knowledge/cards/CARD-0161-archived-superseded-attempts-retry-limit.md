Implementation commit: 86aece0f41895f9318e8b442e26581b0aff7ddba — архивные вытесненные попытки исключены из лимита повторов своей работы

# CARD-0161: архивные вытесненные попытки вне лимита повторов

## HEAD

Status: Implemented and tested — awaiting Review
Branch: factory/3420e685-419-658317c6-aba
Specification: `knowledge/specs/archived-superseded-attempts-do-not-spend-retry-limit.md`
Implementation commit: `86aece0f41895f9318e8b442e26581b0aff7ddba`.
What changed: общий счётчик исключает task ID из `archived_attempts` только
для своего `work_id`; legacy-работы сопоставляются по заголовку, повреждённые
метаданные не уменьшают счётчик.
Evidence: `python3 -m unittest pilot.test_pilot.CorrectionProvenanceStormTests pilot.test_pilot.WorkArchiveCleanupTests` → 20 tests, OK.
Evidence: `just build` → три Factory binary собраны успешно.
One next action: Review должен проверить фильтрацию и изоляцию одноимённых работ.

## LOG

### 2026-08-14 — Specification

Фактическая причина локализована: архиватор уже сохраняет ID вытесненных задач
в `works.json.archived_attempts`, но `stage_attempts` считает все совпавшие
задачи и не читает архивную квитанцию. Определены точечное изменение Pilot,
защита от смешения одноимённых работ и обязательная регрессия без изменений UI,
API или схемы данных.

### 2026-08-14 — Implement

`stage_attempts` теперь читает архивные квитанции текущего поколения работы и
не считает вытеснённые task ID, сохраняя прежний учёт всех неархивных попыток.
Регрессии покрывают текущую/архивную пару, отсутствие квитанции, одинаковые
заголовки разных `work_id`, отсутствующие и повреждённые метаданные. Целевые 20
тестов прошли; `just build` успешно собрал три binary.

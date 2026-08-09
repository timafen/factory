# CARD-0034 — Встроенный патруль конвейера Фабрики

## HEAD

- Status: Specification ready for implementation.
- Branch: `factory/022b43d8-410-8534c8bf-4a2`.
- Specification: `knowledge/specs/internal-factory-pipeline-patrol.md`.
- Scope: автономный контракт `pipeline_watch` в `pilot/pilot.py` и целевые тесты в `pilot/test_pilot.py`; без нового демона, cron, API или миграции данных.
- Acceptance proof: `python3 -m unittest pilot.test_pilot.PipelineWatchTests`.
- One next action: реализовать и доказать идемпотентное возобновление потерянного перехода тестами.

## LOG

### 2026-08-08 — Specification

Зафиксирован минимальный путь: существующий pilot патрулирует переходы сам, ждёт безопасное окно, не дублирует живую работу и после двух толчков сообщает владельцу об остановке. Внешний LLM-помощник, отдельный процесс и новый планировщик не участвуют. Спецификация содержит проверяемые обещания по двум файлам реализации и целевой команде теста.

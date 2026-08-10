# CARD-0048 — Очистка забытого приостановленного конвейера

## HEAD

- Status: Specification ready — ожидает реализации.
- Branch: `factory/8e5bde0f-635-76e66a26-65d`.
- Specification: `knowledge/specs/orphaned-paused-pipeline-cleanup.md`.
- What changes: пауза без открытой карточки Плана, открытого вопроса и живой
  задачи перестаёт бессрочно блокировать новый конвейер с тем же названием.
- Implementation scope: `pilot/pilot.py`, `pilot/test_pilot.py`.
- Required check:
  `python3 -m unittest pilot.test_pilot.OrphanedPausedPipelineCleanupTest`.
- One next action: реализовать согласованную сверку и целевые тесты.

## LOG

### 2026-08-10 — Specification

Зафиксирован минимальный контракт очистки осиротевшей паузы. Пауза сохраняется,
если у работы остаётся хотя бы одно видимое основание: незавершённая карточка
Плана, открытый вопрос владельцу или живая задача конвейера. Форматы данных и API
не меняются; обязательная проверка привязана к новому регрессионному классу.

Implementation commit: a0570fc797bdc64c11b7355602d0703123a755c4 — Factory удаляет недоступные старые поколения после успешного выпуска

# CARD-0179: Проверка зарегистрированного origin

## HEAD

Status: Planned
Branch: factory/7ae7bc34-8b8-2a2890d0-a9a
Specification: `knowledge/specs/registered-origin-verification.md`
What changed: определена защита временных Git-репозиториев от подменённого или
неожиданного `origin` до любого чтения, сравнения или публикации ветки.
Evidence: будущая реализация добавит `TemporaryRepositoryOriginTest` и выполнит
`python3 -m unittest pilot.test_pilot.TemporaryRepositoryOriginTest`.
One next action: Implement добавляет общий helper и тесты только в `pilot/`.

## LOG

### 2026-08-15 — Specification

Зафиксировано, что `fresh_branch_snapshot()`, `refresh_stale_branch()` и
`rebuild_clean_branch()` создают временный Git-репозиторий, регистрируют `origin`
и затем используют его для сетевых операций. Реализация обязана прочитать URL
зарегистрированного remote и сверить его с каноническим URL проекта сразу после
регистрации. Любая неопределённость блокирует поток до первой потенциально
опасной Git-команды и не меняет рабочую ветку исполнителя.

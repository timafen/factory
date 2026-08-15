Implementation commit: 1b465e687e07874d07a83ee17dde01ba69f2b79a — Factory проверяет зарегистрированный origin до сетевых Git-операций

# CARD-0179: Проверка зарегистрированного origin

## HEAD

Status: Implemented
Branch: factory/cfdbc503-816-7fc68d57-4d4
Specification: `knowledge/specs/registered-origin-verification.md`
What changed: временные review, refresh и rebuild сверяют зарегистрированный
`origin` сразу после добавления; ошибка не раскрывает URL и останавливает поток.
Evidence: `TemporaryRepositoryOriginTest` → 4 tests OK; `FreshDefaultBranchSnapshotTests` → 16 tests OK.
One next action: Review проверяет поставку и контракт блокировки на полном diff.

## LOG

### 2026-08-15 — Specification

Зафиксировано, что `fresh_branch_snapshot()`, `refresh_stale_branch()` и
`rebuild_clean_branch()` создают временный Git-репозиторий, регистрируют `origin`
и затем используют его для сетевых операций. Реализация обязана прочитать URL
зарегистрированного remote и сверить его с каноническим URL проекта сразу после
регистрации. Любая неопределённость блокирует поток до первой потенциально
опасной Git-команды и не меняет рабочую ветку исполнителя.

### 2026-08-15 — Implement

Добавлен общий безопасный контроль URL зарегистрированного `origin` во всех трёх
временных Git-потоках до первой сетевой операции. Подмена, отсутствие или ошибка
чтения блокируют review/refresh и останавливают rebuild без публикации.
Проверено `TemporaryRepositoryOriginTest` (4 OK) и
`FreshDefaultBranchSnapshotTests` (16 OK).

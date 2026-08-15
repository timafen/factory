Implementation commit: 5a3d7de53b7a5ceacbd84b95fa2c1d4c16d6cea2 — текущая реализация release-driver и fixture транзакции выпуска, на которых зафиксирован контракт; исправление повторного SHA передаётся в Implement

# CARD-0302: Повторный выпуск той же версии сохраняет rollback-точку

## HEAD

- Status: Specification ready — awaiting Implement.
- Branch: `factory/82a1e4fb-e01-236f1cac-10e`
- Specification: `knowledge/specs/repeat-release-same-version-no-op.md`
- What changed: только проверяемый контракт для no-op при совпадении полного
  resolved Git SHA; product code и UI на этапе Specification не изменялись.
- Evidence: прочитаны `ops/fx-factory-release` и
  `ops/test-fx-factory-release.sh`; текущий driver всегда создаёт новый
  `release_id` и вращает current/previous, а fixture пока не покрывает A → A.
- One next action: Implement добавляет ранний SHA guard и сценарий A → A → B.

## LOG

### 2026-08-15 — Specification

Зафиксировано, что «та же версия» — это полный SHA после
`git rev-parse HEAD`, а не subject, ref или `release_id`. В валидной
non-bootstrap истории повторный SHA должен завершаться до gates, build,
snapshot и остановки служб, сохраняя targets current/previous, manifest и
metadata. Новый SHA обязан проходить прежнюю ротацию.

Карточка с путём `CARD-0302-repeat-release-same-version.md` отсутствовала в
свежем `origin/main` и рабочем дереве; карточки других работ не изменялись.
Ограничение fixture с UID владельца `/usr/bin/stat` перенесено в риски
спецификации и не расширяет область текущего этапа.

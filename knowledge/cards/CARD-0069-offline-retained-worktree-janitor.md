Implementation commit: 635da28eaea2b9073428831a5ec262480ac57509 — санитар очищает локально подтверждённые retained worktrees только у неактивных offline-воркеров.

# CARD-0069 — Санитар retained worktree только для offline-воркера

## HEAD

- Status: Implemented — awaiting verification
- Branch: `factory/8cb1a6b2-529-5eceec3b-b8b`
- Implementation commit: `635da28eaea2b9073428831a5ec262480ac57509`
- What changed: обход выбирает только неактивные offline-регистрации с
  retained worktrees; online, active и пустые offline-регистрации не трогаются.
- Evidence: `bash ops/test-factory-janitor.sh` → PASS; `go test
  ./internal/controlplane -run 'TestHTTPClearRetainedWorktrees(RequiresDirectLoopback)?$' -count=1` → PASS.
- Next action: выполнить независимую проверку перед слиянием.

## LOG

### 2026-08-11 — Implement

Исправлен отбор санитара: только offline-воркер без активных задач и с retained
записями допускается к локальному карантину и точечному API-подтверждению.
Shell-регрессия подтверждает обычную очистку `claude-haiku` и отсутствие обхода
для active, online и пустого offline-снимков. Существующая Go-проверка сохранила
защиту маршрута от недоверенного проксированного запроса.

Implementation commit: 4f1087eecd229c244bb4834e261c419b33019618 — санитар снимает точный фантомный retained worktree и сохраняет существующий неперемещённый результат.

# CARD-0068 — Санитар снимает уже отсутствующий retained worktree

## HEAD

- Status: implemented
- Branch: `factory/c40465b0-00b-560513a9-a16`
- Implementation commit: `4f1087eecd229c244bb4834e261c419b33019618`
- Specification:
  `knowledge/specs/janitor-clears-already-missing-retained-worktree.md`
- What changed: остановленный санитаром `claude-haiku` перестаёт сообщать
  фантомный retained worktree, если точный путь уже отсутствует после prune;
  существующий результат без успешного карантина остаётся защищён.
- Evidence: `bash ops/test-factory-janitor.sh` →
  `TestJanitorClearsRetainedWorktreeAfterQuarantine: PASS`.
- Next action: влить реализацию в `main` после проверки поставки.

## LOG

### 2026-08-11 — Specification

Зафиксирован оставшийся разрыв: `ops/factory-janitor.sh` отправляет подтверждение
только для путей из массива `moved`, поэтому уже отсутствующая запись никогда не
снимается. Выбран локальный и проверяемый критерий после остановки службы и
`git worktree prune`; новый API и состояние БД не требуются.

### 2026-08-11 — Implement

Санитар формирует точное подтверждение после остановки службы и prune как для
перемещённых, так и для уже отсутствующих путей. Целевая shell-регрессия
подтвердила очистку фантома, сохранность существующего неперемещённого каталога,
карантина и журналирование ошибки API.

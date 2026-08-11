Implementation commit: 941520fec219a4274bbb712413ce8d6da472fea4 — исходная точечная очистка retained worktree и защищённый loopback-маршрут, которые эта регрессия сохраняет.

# CARD-0068 — Санитар снимает уже отсутствующий retained worktree

## HEAD

- Status: planned
- Branch: `factory/1039e868-a6e-4c57b0d6-d0c`
- Specification:
  `knowledge/specs/janitor-clears-already-missing-retained-worktree.md`
- What changes: остановленный санитаром `claude-haiku` перестаёт сообщать
  фантомный retained worktree, если точный путь уже отсутствует после prune;
  существующий результат без успешного карантина остаётся защищён.
- Baseline: `941520fec219a4274bbb712413ce8d6da472fea4` содержит текущие
  loopback-защиту и точечное сравнение снимков; коммит новой реализации должен
  заменить ссылку `Implementation commit` на этапе Implement.
- Next action: изменить локальную классификацию путей в санитаре и добавить
  падающую до реализации shell-регрессию.

## LOG

### 2026-08-11 — Specification

Зафиксирован оставшийся разрыв: `ops/factory-janitor.sh` отправляет подтверждение
только для путей из массива `moved`, поэтому уже отсутствующая запись никогда не
снимается. Выбран локальный и проверяемый критерий после остановки службы и
`git worktree prune`; новый API и состояние БД не требуются.

Implementation commit: 4f1087eecd229c244bb4834e261c419b33019618 — санитар снимает точный фантомный retained worktree и сохраняет существующий неперемещённый результат.

# CARD-0068 — Санитар снимает уже отсутствующий retained worktree

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/c40465b0-00b-560513a9-a16`
- Implementation commit: `4f1087eecd229c244bb4834e261c419b33019618`
- Specification:
  `knowledge/specs/janitor-clears-already-missing-retained-worktree.md`
- What changed: остановленный санитаром `claude-haiku` перестаёт сообщать
  фантомный retained worktree, если точный путь уже отсутствует после prune;
  существующий результат без успешного карантина остаётся защищён.
- Evidence: полный набор прошёл: `go test ./...`; в `web` — `npm ci`,
  `npm run lint`, `npm run typecheck`, `npm test` (14 файлов, 145 тестов),
  `npm run build`; все `ops/test-*.sh`. Целевая проверка подтвердила, что
  `attempt-moved` и уже отсутствующий `attempt-missing` отправляются на очистку,
  а существующий `attempt-unmoved` сохраняется.
- Next action: человеку влить реализацию в `main`.

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

### 2026-08-11 — Verify

| Критерий | Проверка | Наблюдение |
| --- | --- | --- |
| Уже отсутствующий retained worktree снимается | `bash ops/test-factory-janitor.sh` | `attempt-missing` вместе с перемещённым путём отправлен в API; тест PASS. |
| Существующий путь после ошибки перемещения не снимается | та же shell-проверка с подменённым `mv` | `attempt-unmoved` не попал в payload и каталог сохранён. |
| Ошибка подтверждения не маскирует результат | та же shell-проверка с ошибкой `curl` | карантин сохранён, в журнале зафиксирована ошибка API. |
| Смежные компоненты не регрессировали | `go test ./...`; frontend: `npm ci`, lint, typecheck, Vitest, build; все `ops/test-*.sh` | Go PASS; Vitest: 14 файлов и 145 тестов PASS; все shell-проверки PASS. |

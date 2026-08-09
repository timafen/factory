# CARD-0045 — Граница переиспользования Bernstein в Factory

## HEAD

- Status: Implement — два замечания ревью исправлены, готово к Review.
- Branch: `factory/989b3a4c-c8b-40f83321-2a1`.
- Head commit: `43a19c6` (`Закрепить источники Bernstein за проверенным снимком`);
  следующий commit меняет только HEAD/LOG карточки.
- Specification: `knowledge/specs/bernstein-reuse-evaluation.md`.
- What changed: README/tree закреплён за commit `f683ce8…`; ошибочный
  `f6bc3b43` в истории заменён на фактический commit тега 3.13.0.
- Evidence: `git ls-remote` → тег `v3.13.0` указывает на `f683ce8…`;
  пять закреплённых URL → HTTP 200; `git diff --check` → PASS.
- One next action: передать два точечных исправления на повторный Review.

## LOG

### 2026-08-09 — Specification

На свежем `origin/main` изучены текущая и целевая архитектуры Factory, а также
исходный снимок Bernstein 3.13.0 `f683ce8dbc6b89d3f91e578cd641d5882bf489dd`. За Factory сохранены admission,
durable state, fleet routing, permissions, provider actions и UI. Для Bernstein
ограничен PoC внутреннего DAG, CLI adapters, worktree, gates и evidence внутри
одной попытки; перенос исходников и второй источник истины отвергнуты. Заданы
восемь критериев проверки и явные условия остановки эксперимента.

### 2026-08-09 — Implement

Продуктовый код намеренно не менялся: утверждённый владельцем результат этого
этапа — новая спецификация сравнения. Проверки обязательных разделов, исходного
commit и лицензионной отметки прошли; трёхточечный diff содержит только карточку
и спецификацию, `git diff --check` не нашёл ошибок.

### 2026-08-09 — Implement

Привязка Bernstein 3.13.0 и все четыре ссылки на исходники исправлены
на фактический commit тега `v3.13.0` — `f683ce8dbc6b89d3f91e578cd641d5882bf489dd`.
Связь тега подтверждена `git ls-remote`; проверки структуры документов и
`git diff --check` прошли. Документы возвращены на повторную проверку;
интеграция до успешного отдельного offline PoC не разрешена.

### 2026-08-09 — Implement

После точечного Review ссылка на README/tree закреплена за commit
`f683ce8dbc6b89d3f91e578cd641d5882bf489dd`, а ошибочный `f6bc3b43` удалён
из исторической записи. Тег `v3.13.0` проверен через `git ls-remote`,
все пять закреплённых URL ответили HTTP 200, `git diff --check` прошёл.

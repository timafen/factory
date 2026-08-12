# CARD-0090: Verify заново закрепляет удалённую ветку перед merge

## HEAD

Status: Verified PASS — awaiting human merge.
Branch: `factory/a62f2494-33b-09586b53-ed1`.
Implementation commit: c4fe862207c73b497bb24afa109d4dd32c47821e — пустая закреплённая поставка возвращается до Review, сравнение использует точные base и candidate SHA.
What changed: Review и Verify закрепляют свежие удалённые SHA; пустой pinned diff возвращает реализацию одним сообщением. Все сравнения области выполняются как `base_sha...candidate_sha`.
Evidence: свежая удалённая база `2a6eb6046f5a595e5156a4ec0300e0a1aa2f6e11` и кандидат `95dc0129f7a7a2be350e79dcc7643abce8a17ec0` закреплены в отдельном bare-репозитории; 7 целевых Python-тестов, Go-набор, 160 UI-тестов, TypeScript и lint прошли.
Next action: выполнить human merge ветки в `main`.

## LOG

### 2026-08-12 — Implement

Перенесены изменения Verify на свежий `origin/main`: обновление удалённого снимка перед merge,
проверка неизменности delivery-ветки и целевые тесты на блокировку устаревшей поставки.
Целевые проверки прошли (6 tests OK), Go-бинарии собираются.

### 2026-08-12 — Implement

Закрыты две гонки после Review: recovery больше не принимает force-push или merge другого SHA,
а `gh pr merge` атомарно ограничен SHA из merge intent. Целевой набор из 11 тестов,
Python compile-check и сборка трёх Go-бинариев прошли.

### 2026-08-12 — Implement

После замечаний Review пустой закреплённый diff теперь возвращает работу в разработку
одним сообщением, а область вычисляется строго по `base_sha...candidate_sha`.
Целевой класс из 5 тестов, compile-check и проверка diff прошли.

### 2026-08-12 — Verify

| Критерий | Команда / проверка | Результат |
|---|---|---|
| Review сравнивает со свежей основной веткой | isolated bare fetch; `2a6eb604...95dc0129` | PASS: default ref `refs/heads/main`, обе SHA закреплены до сравнения |
| Пустая pinned-поставка возвращается до Review | `python3 -m unittest pilot.test_pilot.FreshDefaultBranchSnapshotTests pilot.test_pilot.ImmutableMergeTests` | PASS: 7/7 |
| Force-push после Verify не может быть слит | тот же целевой набор | PASS: проверки до merge и recovery зелёные |
| Соседние Go/UI функции не регрессировали | `go test -timeout 5m ./...`; `npm test -- --run` | PASS; 160/160 UI |
| Типы и стиль | `npx tsc -p tsconfig.app.json --noEmit`; `npm run lint` | PASS |

Полный `python3 -m unittest pilot.test_pilot`: 240 passed, 13 skipped, один тайминговый
сбой release-broker; отдельный повтор сбойного теста прошёл (1/1), целевая область не затронута.

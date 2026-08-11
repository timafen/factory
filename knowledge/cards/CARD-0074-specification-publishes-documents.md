# CARD-0074 — Спецификация публикует документы до передачи в разработку

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/c0f1ac84-c62-bc22090b-fef`.
Implementation commit: cb556b1fae24773d150825dbdeb95fa96e5c4d75 — новая revision Specification публикует документы перед передачей.
- What changed: migration 023 устанавливает точный prompt для включённой
  Specification и сохраняет прежнюю revision в истории. Handoff-тест теперь
  передаёт BRANCH, полный HEAD и PUSHED: yes опубликованной ветки.
- Evidence: `go test ./...` → PASS; `python3 -m unittest pilot.test_pilot` → 176 tests, OK; `git diff --check origin/main...HEAD` → PASS.
- Next action: Human merges the verified branch.

## LOG

### 2026-08-11 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Upgrade устанавливает revision 023 и сохраняет историю | `go test ./...` | PASS, включая `internal/controlplane` |
| Инструкция требует только документы, commit/push и BRANCH/HEAD/PUSHED | upgrade-тест с точным текстом revision | PASS |
| Опубликованная непустая ветка запускает один Implement | `python3 -m unittest pilot.test_pilot` | PASS, 176 tests |
| Отсутствующая, пустая и недоступная ветка не запускают Implement | `SpecificationBranchHandoffTests` в полном наборе pilot | PASS |
| Ворота Review/Verify, delivery и код приложения не изменены | `git diff --name-only origin/main...HEAD` | PASS: затронуты только migration, regression-тесты и документы |

Полный набор прошёл после чистого запуска. Спецификация исправлена: обе ссылки
на карточку синхронизированы с CARD-0074, как в миграции и установленной revision.

### 2026-08-11 — Implement

Добавлена immutable migration 023: она создаёт детерминированную revision для
включённой Specification, требует документ, карточку CARD-0074, commit/push и
строки BRANCH/HEAD/PUSHED. Upgrade-тест подтверждает exact prompt, историю,
request key и неизменность disabled workflow; handoff-тест сохраняет строгую
проверку опубликованной непустой ветки. Целевые Go и Python проверки прошли.

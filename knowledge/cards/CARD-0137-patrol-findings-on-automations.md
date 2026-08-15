# CARD-0137 — Патрули и находки на экране «Автоматизации»

Implementation commit: cd781011f4db035a982ad288f3356a123d31ae35 — патрули скрыты на экране «Работа», а их находки и итоги перенесены в историю Automation.

## HEAD

Status: IMPLEMENTED — препятствия прошлого Verify устранены
Branch: factory/5d2c3ee1-280-555865f1-50f
Implementation commit: cd781011f4db035a982ad288f3356a123d31ae35 — патрули скрыты в обоих режимах «Работы», а результаты последней попытки доступны в Automation
What changed: Tasks получают устойчивый `work_class`; UI исключает patrol из списка и доски этапов. Находки и итог проецируются из последней попытки; helpers вынесены из React-компонента, `web/dist` пересобран.
Evidence: 2 целевых Go-теста и 26 UI-тестов — PASS; lint без предупреждений, typecheck и production build — PASS.
Next action: повторить Verify на чистой доставленной ветке.

## LOG

### 2026-08-15 — Implement

Исправлена ссылка на реальный коммит реализации, предшествующий обновлению
карточки после ребейза: он содержит встроенную production-сборку переноса патрульных находок.
Ветка сдачи указана как `factory/5d2c3ee1-280-555865f1-50f`.

### 2026-08-14 — Implement

Реализован перенос патрульных задач из экрана «Работа» в историю запусков Automation.
Добавлены проекция последней попытки, разбор канонических `НАХОДКА:` и нейтральный итог без результата.
Целевые web-тесты: 17 passed; полный Go-набор и web typecheck/lint/build прошли.

### 2026-08-14 — Implement

На ветке сдачи заново подтверждены классификация патрулей и проекция последней
попытки: целевой Go-набор, 17 UI-проверок, typecheck, lint и production build
прошли. CARD-0129 дополнена обязательной стабильной ссылкой на коммит реализации.

### 2026-08-14 — Implement

Исправлены все замечания повторного Review: режим «по этапам» не показывает
патрули, разбор находок работает с LF/CRLF, Store и HTTP API проверены для
пустой попытки, retry, error и result. Целевые проверки и production build прошли.

### 2026-08-14 — Verify

| Критерий / проверка | Команда | Результат |
| --- | --- | --- |
| Классификация, latest attempt, retry/result/error/empty | `just check` (Go-часть) | PASS: все Go-пакеты, включая `internal/controlplane`, прошли |
| Патрули скрыты в обоих Work-режимах; обычные задачи сохранены; находки и итоги показаны | `cd web && npm test -- --run src/Work.test.ts src/WorkView.test.tsx src/Automations.test.tsx` | PASS: 25 тестов |
| Контракт TypeScript | `cd web && npm run typecheck` | PASS |
| Production build и embedded UI | `just test-browser` | FAIL: сборка меняет отслеживаемый `web/dist`; Playwright не запущен |
| Lint | `just ui-check` | FAIL: 2 warning `react-refresh/only-export-components` в `Automations.tsx:1148,1155` |
| Tooling/launcher | `env -u FACTORY_BUILD_DIR just test-tooling`; `just test-launcher` | PASS |

Pinned comparison: base `997953e184cb76a4fb222c1c21bd210692953089`,
candidate `fbba4615c1ee1d40b057bcca56d4b8a28de78ae1`. Рабочее дерево до
проверки было чистым; тестовые build-артефакты удалены. Verdict: BLOCKED.

### 2026-08-14 — Implement

Исправление заново собрано от свежего `origin/main`: helpers вынесены из
`Automations.tsx`, ссылки тестов обновлены, production bundle зафиксирован.
Целевые Go/UI-тесты, lint, typecheck и production build прошли.

# CARD-0137 — Патрули и находки на экране «Автоматизации»

## HEAD

Status: BLOCKED — Verify выявил lint-warning и незафиксированный embedded UI
Branch: factory/201d3c5f-8d0-effdd4a6-7de
Implementation commit: 8f0cf36a7da88607bf322863e3ce92786d7e4bac — патрули скрываются в обоих режимах «Работы», а результаты последней попытки подтверждены через Store и HTTP API
What changed: Tasks получают устойчивый `work_class`; UI исключает patrol в списке и доске этапов, а находки понимают настоящие LF/CRLF. Последняя попытка проецирует retry, result/error и пустое состояние.
Evidence: полный Go-набор и 25 целевых UI-тестов прошли; `just ui-check` остановился на двух `react-refresh/only-export-components` warning, а `just test-browser` обнаружил отличающийся `web/dist` до запуска Playwright.
Next action: вынести экспортируемые helpers из `Automations.tsx` и закоммитить результат `npm run build`, затем повторить Verify.

## LOG

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

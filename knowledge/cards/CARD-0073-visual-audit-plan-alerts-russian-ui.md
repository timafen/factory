# CARD-0073 — Визуальный аудит Плана, Уведомлений и русского интерфейса

## HEAD

- Status: BLOCKED — committed `web/dist` не воспроизводится, а rebase на свежий `main` конфликтует в UI-файлах.
- Branch: `factory/5ca3b3c2-88a-882ecf3c-5c1`.
Implementation commit: aad2e2236733c6faf9d7395a6bc86f59e78ccf17 — усилен locator кнопки сохранения Settings.
- What changed: Settings E2E scoped к `.settings-page`; кнопка выбирается exact role/name без `.first()`.
- Evidence: `npm run test:browser` успешно собрал UI, но `git diff --exit-code -- dist` обнаружил новый `index-BnohdI1Y.js` вместо committed `index-BK4d6-ve.js`; Playwright не был запущен. Rebase на свежий `main` остановился на конфликтах `web/dist`, `web/dist/index.html` и `web/src/Work.tsx`.
- One next action: интегрировать свежий `main`, воспроизвести и закоммитить корректный `web/dist`, затем один раз запустить полный browser-suite.

## LOG

### 2026-08-11 — Implement

Добавлены реальные router-backed browser-проверки Плана и Уведомлений со
снимками для 1440 px и 390 px. План скрывает обоснование до раскрытия, а
Уведомления показывают до 30 свежих событий в сворачиваемых группах. Русские
labels и responsive-правила проверены Vitest, Playwright, lint, typecheck,
сборкой и `go test ./...`; полный browser suite оставлен этапу Verify.

### 2026-08-11 — Implement

Исправлены четыре замечания Review: внешний redirect Плана, русские TaskDetail
и DelegateModal, а также общий словарь состояния, обновления, ошибок и повторов.
Проверены `Location`, role/name selectors и сохранение ID/SHA; intake-аудит прошёл
на 1440/390, как и общий control-plane аудит. После ребейза intake fixture также
получил отдельный свободный порт; полный browser suite остаётся этапу Verify.

### 2026-08-11 — Verify

| Критерий | Проверка | Наблюдение |
|---|---|---|
| План и Уведомления говорят по-русски на 1440/390 | `npm run test:browser` → `web/e2e/intake.spec.ts` | Оба intake-теста прошли; раскрытие причин, переход `?group=stuck`, ссылка `/work/stuck` и отсутствие горизонтального скролла подтверждены. |
| Work, Automations, TaskDetail и DelegateModal доступны на 1440/390 | `npx playwright test e2e/control-plane.spec.ts -g 'audits every Factory screen'` | 1 passed; layout-аудит проверил отсутствие горизонтального overflow, клиппинга интерактивных элементов и перекрытия sticky actions; 12 PNG сохранены в `/opt/factory-data/visual-acceptance/CARD-0073/`. |
| ID/SHA/диагностика сохраняются | `go test -timeout 5m ./...`; UI Vitest; browser assertions | Go и UI тесты прошли; browser suite дошёл до сценариев сохранения, но остановился на устаревшем тексте Worker Settings. |
| Полный browser suite | `npm run test:browser` (ровно один запуск) | FAIL: 9 passed, 1 failed, 12 did not run. Тест ожидает английское `restart the worker`, UI показывает русское `Обнови файл и перезапусти исполнителя`. |
| Go/UI gates | `go vet ./...`, gofmt-check, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build` | Все PASS; после `npm ci` зависимости были установлены в ignored `web/node_modules`. |

Скриншоты сохранены вне Git; бинарники в репозиторий не добавлялись. Код не изменялся.

### 2026-08-11 — Implement

Обновлено только устаревшее ожидание Worker Settings: тест проверяет актуальную
русскую фразу «Обнови файл и перезапусти исполнителя». Production UI не менялся.

### 2026-08-11 — Verify

| Критерий | Проверка | Наблюдение |
|---|---|---|
| Полный Go/UI/lint/typecheck/build gate | `just check`; `npm run build`; `FACTORY_BUILD_DIR=/tmp/card-0073-build just build` | PASS: Go tests, vet, vuln, staticcheck, format, boundary, tooling, launcher; 15 UI-файлов и 157 UI-тестов; production UI и три Go-бинарника собраны. |
| Русский Plan/Alerts и отсутствие overflow | `npx playwright test` (один запуск), tests 13, 21, 22 | PASS: 22 теста начаты; visual audit desktop/phone, narrow grouped layout, Plan и Alerts прошли. 55 PNG присутствуют в `web/test-results/screenshots`; audit проверил horizontal overflow и клиппинг. |
| Все browser-сценарии | `npx playwright test` (один запуск) | FAIL: 16 passed, 1 failed, 5 did not run. `manages repository routing...` завис на `getByLabel('Canonical identity')` в `web/e2e/control-plane.spec.ts:1161`; timeout 120s. |
| Browser wrapper и committed dist | `npm run test:browser` (один запуск) | FAIL до Playwright: build создал `index-BK4d6-ve.js`, а committed dist ссылается на `index-BLGRwC7Z.js`; `git diff --exit-code -- dist` остановил wrapper. |
| Cleanup и дерево | process/port check; `git status --short` | Test-specific Playwright/server processes завершились; generated dist восстановлен, рабочее дерево чистое. |

Итог: Verify FAIL. Код не изменялся; изменена только эта карточка для фиксации evidence.

### 2026-08-11 — Implement

Исправлены соседние assertions сценария repository routing: «Точная идентичность»,
«Добавить репозиторий», русское резюме готовности и действия маршрутизации. `web/dist`
обновлён результатом `npm run build`; targeted repository Playwright, visual audit и
157 UI-тестов прошли.

### 2026-08-11 — Verify

| Критерий | Проверка | Наблюдение |
|---|---|---|
| Полный Go/UI/lint/typecheck gate | `just check` | PASS: Go format/vet/vuln/staticcheck/boundary, все Go-тесты, ESLint, TypeScript, 15 UI-файлов и 157 тестов, tooling и launcher. |
| Production build | `FACTORY_BUILD_DIR=$(mktemp -d /tmp/card-0073-build.XXXXXX) just build` | PASS: собраны три бинарника в изолированный `/tmp` каталог. |
| `web/dist` воспроизводим | `npm run test:browser` (единственный запуск полного wrapper) | PASS: `npm run build` завершился, `git diff --exit-code -- dist` прошёл до Playwright. |
| Русский Plan/Alerts, desktop/phone visual audit, routing и overflow | `npm run test:browser` | PASS: тесты Plan/Alerts на desktop и phone прошли; visual audit и проверки overflow прошли до сбоя. |
| Все браузерные сценарии | `npm run test:browser` (ровно один запуск) | FAIL: 20 passed, 1 failed, 1 did not run. Первый сбой: `web/e2e/control-plane.spec.ts:1484`, сценарий `migrates a locked legacy snapshot through Resume and Finalize`; в диалоге `Перенести старый опросчик` не найдена кнопка `Review E2E imported legacy issues`. |
| Cleanup и дерево | process/port check; `git status --short` | PASS: процессы/серверы этого прогона завершились, рабочее дерево чистое до записи этой карточки; сторонние процессы не затрагивались. |

Итог: Verify FAIL. Код не изменялся; эта запись фиксирует полный прогон и первый точный сбой.

### 2026-08-11 — Implement

После review исправлен ослабленный locator около `control-plane.spec.ts:1502`:
тест ограничен Settings-контейнером и использует `getByRole("button", { name: "Сохранить настройки", exact: true })`.
Убран `.first()`, поэтому дубликат кнопки или неверная область теперь ломают сценарий.
Targeted Playwright: `audits every Factory screen on desktop and phone`, legacy migration и Settings — 3 passed.

### 2026-08-11 — Verify

| Критерий | Проверка | Наблюдение |
|---|---|---|
| Полный Go/UI gate | `just check` | BLOCKED: vet, vuln и staticcheck прошли; затем нетронутый `internal/worker.TestCancellationStopsCompleteProcessGroup` превысил timeout 300 s. |
| Воспроизводимость committed UI | `cd web && npm ci --no-audit --no-fund`, затем `npm run test:browser` | BLOCKED: `tsc -b && vite build` прошёл, но guard `git diff --exit-code -- dist` обнаружил `index-BnohdI1Y.js` вместо `index-BK4d6-ve.js`; Playwright не стартовал. |
| 21 русскоязычный браузерный сценарий | Тот же единственный browser-wrapper | Не проверены: wrapper остановился до запуска сценариев. |
| Чистота дерева | восстановление только build-generated `web/dist`, `git status --short` | PASS до записи evidence; тестовые артефакты не оставлены. |

Итог: BLOCKED. Нельзя подтвердить 21 сценарий, пока committed `web/dist` не станет воспроизводимым. Тайм-аут worker-теста относится к нетронутой области и зафиксирован как находка проекта.

### 2026-08-11 — Verify (rebase)

| Критерий | Проверка | Наблюдение |
|---|---|---|
| Совместимость со свежим `main` | `git fetch origin main && git rebase origin/main` | BLOCKED: конфликт `web/dist/assets/index-FbtnAMaY.js` (rename/delete), `web/dist/index.html` и `web/src/Work.tsx`; rebase отменён без изменения реализации. |

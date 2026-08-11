# CARD-0073 — Визуальный аудит Плана, Уведомлений и русского интерфейса

## HEAD

- Status: Implemented — targeted browser checks pass; full browser suite remains for Verify.
- Branch: `factory/4d1fc847-78d-58c2d589-8aa`.
Implementation commit: 34af0677eb18fa6b3d2e6decbc89b5ae2d679bac — План сохраняет внешний `/intake/plan`, а TaskDetail, постановка задачи и общий словарь переведены.
- What changed: redirect `Location` нормализуется к публичному пути; технические ID/SHA остаются без изменений.
- What changed: intake и control-plane browser fixtures используют раздельные свободные порты после ребейза на `main`.
- Evidence: targeted Worker Playwright and visual audit pass; implementation UI checks remain covered by the source branch evidence.
- Next action: Повторить полный browser suite на этапе Verify.

## LOG

### 2026-08-11 — Implement

Обновлено только устаревшее ожидание Worker Settings: тест проверяет актуальную
русскую фразу «Обнови файл и перезапусти исполнителя». Production UI не менялся.

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

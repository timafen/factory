# CARD-0073 — Визуальный аудит Плана, Уведомлений и русского интерфейса

## HEAD

- Status: Verify FAIL — human merge blocked by an outdated browser expectation.
- Branch: `factory/07abde0f-50d-31baa95e-284`.
Implementation commit: 5442ad5450b3192c99fad32ca5394f2678eb7a59 — План сохраняет внешний `/intake/plan`, а TaskDetail, постановка задачи и общий словарь переведены.
- What changed: redirect `Location` нормализуется к публичному пути; технические ID/SHA остаются без изменений.
- What changed: intake и control-plane browser fixtures используют раздельные свободные порты после ребейза на `main`.
- Evidence: `go test -timeout 5m ./...`, `go vet ./...`, gofmt-check, UI lint/typecheck/Vitest/build → PASS; full `npm run test:browser` → 9 passed, 1 failed, 12 did not run; isolated visual audit → PASS.
- Next action: Обновить устаревшее ожидание `restart the worker` на русскую строку и повторить Verify.

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

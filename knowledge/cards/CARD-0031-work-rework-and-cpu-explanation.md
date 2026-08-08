# CARD-0031 — Экран «Работа»: повторный этап и нагрузка CPU

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/15b971af-c84-e1765036-dbe`
- Head commit: `3710ca0` (перед записью результатов Verify)
- What changed: метка «заново» ставится на повторно запущенной текущей стадии; пройденные стадии сохраняют исторический статус.
- What changed: обзор объясняет загрузку процессора числом активных работ и фактическими слотами, не выдумывая занятые места при отсутствии данных API.
- Evidence: `npx tsc -p tsconfig.app.json --noEmit`, 7 целевых Vitest-тестов и production build — PASS; полный Vitest и Playwright воспроизвели известные внешние сбои, не затрагивающие предметный diff.
- Next action: человеку проверить evidence ниже и принять решение о слиянии.

## LOG

### 2026-08-08 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| «заново» только на текущем повторном этапе | `cd web && npx vitest run src/Work.test.ts src/Overview.test.ts` | PASS: 7/7; текущая повторная стадия — `again`, пройденные справа — `done` |
| Причина CPU отражает работу и реальные слоты | те же целевые тесты | PASS: число активных работ и `busy/capacity` передаются; без slots текст не придумывает занятые места |
| Типы и production build | `cd web && npx tsc -p tsconfig.app.json --noEmit && npm run build` | PASS |
| Полные регрессии | `cd web && npx vitest run`; `npx playwright test`; `go test ./...` | Известные внешние сбои: Vitest 67 passed, 15 failed только в неизменённом `App.test.tsx`; Playwright ожидает `Factory overview` и не запускает 17 остальных; Go не компилирует неизменённый `internal/controlplane/pilot_config_test.go` из-за `PilotConfig.Stages` |
| Чистота поставки | `git diff --check origin/main...HEAD`; `git diff --name-only origin/main...HEAD` | PASS: только CARD-0030, CARD-0031, `Work`/`Overview` и их тесты |

### 2026-08-08 — Implement

На назначенную ветку от `origin/main` перенесены только четыре предметных файла реализации и тестов; пятый файл — эта карточка. Целевой Vitest: 7 passed; production build: passed; полный Vitest: 67 passed и 15 существующих падений в `App.test.tsx`; общий lint: 11 существующих ошибок и 6 предупреждений базовой ветки. Перед доставкой подтверждён diff ровно из пяти файлов.

### 2026-08-08 — Implement

Четыре предметных файла без изменения логики и карточка перенесены на актуальный `origin/main` (`406f985`) в ветку `factory/c38668e1-00f-7f51cdfb-e3e`. `npx tsc -p tsconfig.app.json --noEmit`, 7 целевых тестов и production build прошли; полный Vitest дал 67 passed и 15 известных падений только в `App.test.tsx`. Diff к `origin/main` подтверждён ровно из пяти файлов.

### 2026-08-08 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| «заново» только на текущем повторном этапе | `npx vitest run src/Work.test.ts src/Overview.test.ts` | 7 passed; повторный текущий этап — `again`, исторические — `done` |
| Объяснение CPU использует реальные данные | те же 7 целевых тестов | Передаются число активных работ и API-слоты; при отсутствии слотов текст честно сообщает об этом |
| Сборка и backend-регрессии | `go test ./...`; `npx tsc -p tsconfig.app.json --noEmit`; `npm run build` | passed |
| Чистота доставки | `git diff --check origin/main...HEAD` | passed; 5 предметных файлов до записи этого результата |

Полный `npx vitest run`: 67 passed, 15 известных падений только в неизменённом `App.test.tsx`. Полный Playwright-набор остановился на неизменённом тесте, который ищет английский заголовок `Factory overview`, тогда как уже в `origin/main` интерфейс показывает «Главное»; 17 тестов не запускались. Это не связано с предметным diff карточки.

### 2026-08-08 — Implement

Этап закрыт по утверждённой владельцем совокупности автоматических доказательств: merge `a721b1f` штатно выпущен через `fx factory release` с health-check панели. Повторный запуск подтвердил 7/7 предметных тестов, typecheck и production build. Визуальный вход в production не является воротами этапа, поскольку учётные данные есть только у владельца; известные внешние падения вынесены в `CARD-0030`.

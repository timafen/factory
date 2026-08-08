# Infrastructure findings backlog

### 2026-08-08 — Экран настроек pilot
На ветке `factory/ddaa8de1-fa2-66c96daa-db5` (проверенный HEAD `b279e48`) добавлены безопасный API и `/settings` для `pilot/config.json`.
Список worker ID впервые берётся из уже известных control-plane исполнителей и дальше хранится в настройках; default остаётся `allow_any_worker=true`.
Доказательство: `go test ./...`, `npm test`, `npm run lint`, `npm run build` (результаты зафиксированы в delivery report).
Открытый риск: pilot не участвует в общем межпроцессном lock; конфликт API определяется по версии непосредственно перед atomic replace.

## HEAD
BLOCKED: полный Vitest содержит 15 падений в неизменённом `web/src/App.test.tsx`. Branch: `factory/fb37937b-774-1bec0524-355`. Head commit: `ffc9dc0` до записи результатов проверки.
What changed: проверена поставка выбора пяти групп телефонных уведомлений и её соответствие `NOTIFY_GROUPS`/`NOTIFY_DEFAULTS` пилота.
Evidence: `npx tsc -p tsconfig.app.json --noEmit`, Settings Vitest 5/5, `npx vite build` и `go build ./cmd/factory-server` — PASS; полный Vitest — 69/84, 15 FAIL в `App.test.tsx`.
Next action: исправить или подтвердить как допустимые 15 падений полного Vitest, затем повторить Verify.

## LOG

### 2026-08-08 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Всегда видны пять групп | `src/Settings.test.tsx`: `shows every notification group in Russian...` | PASS: все пять русских подписей найдены |
| Значения берутся из конфигурации и умолчаний | `src/Settings.test.tsx`: `uses pilot defaults when notification groups are absent`; сверка `/opt/factory-data/pilot/pilot.py` | PASS: `questions`, `stuck`, `money`, `done` включены, `routine` выключен; ключи и умолчания совпадают с пилотом |
| Сохраняется полный канонический выбор | `src/Settings.test.tsx`: `shows every notification group in Russian...` | PASS: PUT содержит пять ключей `notify_groups`, изменён `stuck` |
| Сборка frontend | `npx tsc -p tsconfig.app.json --noEmit`; `npx vite build` | PASS |
| Сборка сервера | `go build ./cmd/factory-server` | PASS |
| Полный набор Vitest | `npx vitest run` | BLOCKED: 69/84, 15 падений только в неизменённом `src/App.test.tsx` (включая устаревший `Factory overview`) |

### 2026-08-08 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Экран Settings показывает конфигурацию | `npx playwright test -g 'edits pilot settings from the Settings screen'` | PASS: открыт `/settings`, видны Pilot settings и Brain chain |
| Изменение сохраняется | тот же Playwright-сценарий | PASS: PUT успешен, `poll_seconds` изменён с 10 на 15 и сохранён после reload |
| Некорректная политика worker отклоняется | `go test ./...` (`TestPilotConfigValidationWorkerPolicy`) и `npm test -- --run` | PASS: строгий неизвестный worker отклонён, UI блокирует сохранение |
| Устаревшая версия не перезаписывает файл | `go test ./...` (`TestPilotConfigStorePreservesNotesAndRejectsConflict`) | PASS: conflict отклонён, содержимое файла не изменено |
| Регрессии смежного UI | `npm run test:browser` | BLOCKED: Workers E2E не нашёл `Implement the modern control-plane UI` на `control-plane.spec.ts:563` |

### 2026-08-08 — Implement

Падение Workers оказалось временной гонкой фикстуры: 30-секундные online-окно worker и lease активной попытки истекали во время последовательного suite. Тест поддерживает lease до своего запуска и посылает свежую регистрацию `Build Mac` перед открытием `/workers`. Полный `npm run test:browser` прошёл: 18/18; Go tests/build и frontend test/lint/typecheck/build также прошли.

### 2026-08-08 — Implement

Поле Configuration note теперь всегда видно и позволяет создать отсутствующий `_note`; регрессионный Vitest проверяет пустое поле и отправку новой заметки. Исправлены фактические branch/HEAD исходной реализации. Доказательство: `go test ./...`, `go build ./...`, `npm test -- --run` (75), `npm run lint`, `npm run typecheck`, `npm run build` и `npm run test:browser` (18) — PASS.

### 2026-08-08 — Implement

В HEAD записан последний содержательный коммит `5d49ada`. Верхний коммит поставки является служебной правкой только этой карточки; при проверке HEAD допустим как родитель вершины ветки. Содержательная реализация и результаты её проверок не изменялись.

### 2026-08-08 — Известные регрессии проверок экрана «Работа»
На ветке `factory/15b971af-c84-e1765036-dbe` предметные Vitest-тесты (7/7), typecheck и production build прошли; релиз `a721b1f` ранее прошёл штатный health-check.
Полный Vitest имеет 15 известных падений в неизменённом `App.test.tsx`, а Playwright ожидает устаревший английский заголовок `Factory overview` вместо «Главное»; по решению владельца они не входят в этап.
Дополнительно текущий `go test ./...` не компилирует неизменённый `internal/controlplane/pilot_config_test.go` из-за рассинхронизации типа `PilotConfig.Stages`; предметный код карточки 0031 это не затрагивает.
Риск: общие наборы останутся красными до отдельных исправлений тестовой инфраструктуры.

### 2026-08-08 — Группы уведомлений на телефон
На ветке `factory/669ce695-1fb-ea64ee84-688` экран Settings получил пять канонических групп и умолчания из pilot.py.
Выбор сохраняется полным `notify_groups`; Vitest Settings 5/5, focused ESLint, typecheck, frontend build и `go build ./...` прошли.
Открытый риск: общие Vitest/lint и `go test ./...` остаются красными на ранее существующих сбоях вне изменённых файлов.

### 2026-08-08 — Чистая поставка групп уведомлений
На ветке `factory/d6cf72b6-b10-192d4077-721` предметный коммит перенесён на свежий `origin/main` без изменений Work, API статуса, навигации и CARD-0031.
Доказательство: Settings Vitest 5/5, typecheck, frontend build, `go build ./...` и `git diff --check origin/main` — PASS.
Открытый риск: полные Vitest/lint и `go test ./...` сохраняют известные сбои в неизменённых файлах базы.

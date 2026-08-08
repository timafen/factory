# Infrastructure findings backlog

### 2026-08-08 — Экран настроек pilot
На ветке `factory/ddaa8de1-fa2-66c96daa-db5` (проверенный HEAD `b279e48`) добавлены безопасный API и `/settings` для `pilot/config.json`.
Список worker ID впервые берётся из уже известных control-plane исполнителей и дальше хранится в настройках; default остаётся `allow_any_worker=true`.
Доказательство: `go test ./...`, `npm test`, `npm run lint`, `npm run build` (результаты зафиксированы в delivery report).
Открытый риск: pilot не участвует в общем межпроцессном lock; конфликт API определяется по версии непосредственно перед atomic replace.

## HEAD
BLOCKED: full suite не проходит; ветка содержит незаявленные изменения помимо Settings. Branch: `factory/af1ffd51-c1e-39c7a04a-7d9`. Head commit: `089c270`.
What changed: относительно `origin/main` изменены 6 файлов, включая `pilot/pilot.py`, `web/src/App.tsx` и `web/src/Work.tsx`; это противоречит заявлению о двух файлах Settings.
Evidence: `npx vitest run src/Settings.test.tsx` — PASS (4/4); typecheck, lint и build — PASS. `go test ./...` — FAIL: `internal/controlplane/pilot_config_test.go` не компилируется. Целевой Playwright — FAIL: `e2e/control-plane.spec.ts:1107` ожидает устаревший заголовок `Pilot settings`.
Next action: вернуть поставку к изолированным Settings-изменениям и обновить e2e-проверку русских текстов, затем повторить verify.

## LOG

### 2026-08-08 — Implement (пересборка ветки)

Прошлая поставка (`factory/b2ac3700-bbb-471a9799-086`, HEAD `4725a7e`) была основана на устаревшем `main` и тянула 24 несвязанных файла (intake, pilot, ops, экраны Work/Overview, навигация). По решению владельца ветку пересобрали с нуля: `git fetch origin`, новая ветка от свежего `origin/main` (`9e46f22`), затем `git checkout 4725a7e -- web/src/Settings.tsx web/src/Settings.test.tsx` — только эти два файла, без merge/rebase старой ветки. `git diff --name-only origin/main` подтверждает ровно 2 файла. Проверки: `npx tsc -p tsconfig.app.json --noEmit`, `npx vitest run src/Settings.test.tsx` (4/4), `npx eslint`, `npm run build` — все PASS.

### 2026-08-08 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Русские названия полей Settings | `npx vitest run src/Settings.test.tsx` | PASS: 4/4, включая русские labels |
| Пояснение к каждой группе и полю | тот же тест и typecheck | PASS: тест проверяет пояснения; обязательный `hint` в типах компонентов не допускает поле без него |
| Сохранение настроек | тот же тест | PASS: PUT содержит изменённый `poll_seconds` и `_note` |
| Полный Go-suite | `go clean -testcache && go test ./...` | FAIL: `pilot_config_test.go` использует несовместимый тип `PilotConfig.Stages` |
| Browser-проверка Settings | `npx playwright test -g 'edits pilot settings from the Settings screen'` | FAIL: сценарий ожидает английский `Pilot settings` в строке 1107 |
| Состав поставки | `git diff --name-only origin/main...HEAD` | FAIL: 6 файлов вместо заявленных 2; добавлены несвязанные `pilot/pilot.py`, `App.tsx`, `Work.tsx` |

Статус: BLOCKED — релиз и слияние не выполнялись.

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

# Infrastructure findings backlog

### 2026-08-08 — Экран настроек pilot
На ветке `factory/ddaa8de1-fa2-66c96daa-db5` (проверенный HEAD `b279e48`) добавлены безопасный API и `/settings` для `pilot/config.json`.
Список worker ID впервые берётся из уже известных control-plane исполнителей и дальше хранится в настройках; default остаётся `allow_any_worker=true`.
Доказательство: `go test ./...`, `npm test`, `npm run lint`, `npm run build` (результаты зафиксированы в delivery report).
Открытый риск: pilot не участвует в общем межпроцессном lock; конфликт API определяется по версии непосредственно перед atomic replace.

## HEAD
BLOCKED: ветка Settings содержит несвязанные изменения относительно `origin/main`. Branch: `factory/bf4e3ba5-e10-5789a27b-505`. Head commit: `58f3142`.
What changed: предметная реализация русских названий и пояснений проверена, но вместе с ней в поставку попали `Overview`, `Summary`, `pilot.py` и карточка CARD-0032.
Evidence: `npm test` (32 PASS), `npm run typecheck`, `npm run build`, `go test ./...` и предметный Playwright — PASS; `npm run lint` — FAIL (10 существующих ошибок вне Settings); `git diff --name-only origin/main...HEAD` показывает 16 файлов вместо объёма задачи.
Next action: доставить чистую ветку, содержащую только изменения Settings и необходимые тестовые/сборочные артефакты.

## LOG

### 2026-08-08 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Русские названия и пояснения полей Settings | `npm test` | PASS: 32 теста, включая 4/4 `Settings.test.tsx` и проверку русских названий/пояснений |
| Изменение Settings сохраняется | `npx playwright test -g 'edits pilot settings from the Settings screen'` | PASS: `.last-run.json` содержит `status: passed` |
| Сборка и серверный код | `npm run typecheck`, `npm run build`, `go test ./...` | PASS |
| Смежные регрессии | `npm run lint` | FAIL: 10 ошибок в `Access.tsx`, `Live.tsx`, `Pipeline.tsx`, `Say.tsx`, не относящихся к Settings |
| Чистота поставки | `git diff --name-only origin/main...HEAD`, `git diff --check origin/main...HEAD` | BLOCKED: формат чист, но 16 изменённых файлов включают несвязанные `Overview`, `Summary`, `pilot.py`, CARD-0032 |

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

### 2026-08-08 — Настройки: русские названия полей и пояснение к каждому
На ветке `factory/bf4e3ba5-e10-5789a27b-505` (HEAD `3f6afbc`) экран `/settings` переведён на русский, к каждому полю добавлена подсказка-пояснение. Работа перенесена с прежней ветки `factory/af1ffd51-c1e-39c7a04a-7d9`, но отрезана заново от свежего `origin/main` — лишние файлы прошлой ветки (`pilot.py`, `CARD-0032`, `Summary.tsx`, `whatChanged.ts`) не переносились, взяты только `Settings.tsx`/`Settings.test.tsx` плюс правка Playwright-сценария под новые тексты.
По пути найдены и исправлены два независимых, ранее существовавших на `main` бага, без которых сценарий Settings невозможно было проверить: `internal/controlplane/pilot_config_test.go` использовал устаревший формат `Stages` (словарь вместо списка) и не давал собрать пакет `controlplane`; фикстура `web/e2e/server.mjs` писала `stages` в том же устаревшем формате, из-за чего бэкенд отвечал `pilot_config_invalid` (503) и Settings-сценарий Playwright падал ещё до открытия экрана.
Доказательство: `npx vitest run src/Settings.test.tsx` (4/4), `npm run typecheck`, `npm run build`, `go test ./internal/controlplane/...` (все pilot-тесты зелёные), `npx playwright test -g 'edits pilot settings from the Settings screen'` (PASS).
Открытый риск: в `internal/controlplane` остаётся один не связанный с настройками провал — `TestHTTPManagedRepositoryCatalog` падает на `GET /api/v1/workers/{id}/repository-options` (404), потому что для этого маршрута нет регистрации в `http.go`; это отдельный, самостоятельный баг про управляемые репозитории, не в рамках этой задачи.

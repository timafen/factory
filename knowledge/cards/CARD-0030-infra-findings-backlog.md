# Infrastructure findings backlog

### 2026-08-08 — Экран настроек pilot
На ветке `factory/ddaa8de1-fa2-66c96daa-db5` (проверенный HEAD `b279e48`) добавлены безопасный API и `/settings` для `pilot/config.json`.
Список worker ID впервые берётся из уже известных control-plane исполнителей и дальше хранится в настройках; default остаётся `allow_any_worker=true`.
Доказательство: `go test ./...`, `npm test`, `npm run lint`, `npm run build` (результаты зафиксированы в delivery report).
Открытый риск: pilot не участвует в общем межпроцессном lock; конфликт API определяется по версии непосредственно перед atomic replace.

## HEAD
Status: Verified PASS — awaiting human merge. Branch: `factory/aa9fa343-b22-839eaa45-305`. Head commit: `4c6992e`.
What changed: в Settings добавлены пять русских переключателей групп уведомлений с каноническими ключами и умолчаниями пилота.
Evidence: чистая установка `npm ci`; `npm run typecheck`, `npm run build`, `go build ./...` и `npx vitest run src/Settings.test.tsx` (5/5) — PASS. Полный `npx vitest run`: 15 известных падений только в неизменённом `src/App.test.tsx`, 73/88 всего; `go test ./...` не компилирует старый `internal/controlplane/pilot_config_test.go`.
Next action: человек проверяет и объединяет ветку в `main`; выпуск выполняется через `fx factory release` после merge.

## LOG

### 2026-08-08 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Всегда видны пять групп | `npx vitest run src/Settings.test.tsx` | PASS: найдены все пять русских переключателей |
| Значения берутся из `notify_groups` и умолчаний | тест `uses pilot defaults when notification groups are absent` | PASS: первые четыре включены, `routine` выключена |
| Сохранение сохраняет полный выбор | тест `shows every notification group in Russian and saves the changed selection` | PASS: PUT содержит `questions`, `stuck`, `money`, `done`, `routine` |
| Сборка и типы | `npm run typecheck`; `npm run build`; `go build ./...` | PASS |
| Смежные проверки | `npx vitest run`; `go test ./...`; `npm run test:browser` | 15 старых падений `App.test.tsx`; старый `pilot_config_test.go` не компилирует; Playwright падает на прежнем `Factory overview` до Settings |
| Чистота предметного diff | `git diff --check`; `git diff --name-only 3a055d8...3ff898b` | PASS: семь файлов задачи, без пробельных ошибок |

### 2026-08-08 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Всегда видны пять групп | `npx vitest run src/Settings.test.tsx` | PASS: 5/5; тест находит «Вопросы ко мне», «Работа встала», «Деньги и лимиты», «Завершения и запуски задач», «Рабочая рутина» |
| Значения берутся из `notify_groups` и умолчаний | тот же набор, тест `uses pilot defaults when notification groups are absent` | PASS: первые четыре группы включены, `routine` выключена |
| Сохраняются пять канонических ключей без потери настроек | тот же набор, тест `shows every notification group in Russian and saves the changed selection` | PASS: PUT содержит `questions`, `stuck`, `money`, `done`, `routine`; существующие `_note` сохранены |
| Типы и production build | `npx tsc -p tsconfig.app.json --noEmit`; `npx vite build`; `go build ./...` | PASS |
| Состав и качество диффа | `git diff --name-only origin/main...HEAD`; `git diff --check origin/main...HEAD` | PASS: ровно 8 заявленных файлов, пробелов/маркеров отладки нет |
| Полный Vitest | `npx vitest run` | Известная база: 15 падений только в неизменённом `src/App.test.tsx`; 69 passed, не регрессия поставки |

Смежные общие проверки: `go test ./...` падает на неизменённом `TestHTTPManagedRepositoryCatalog` (404 вместо 200); `npm run lint` — на 11 ошибках вне изменённых файлов; полный и settings Playwright — на прежних ожиданиях экрана/навигации. Эти сбои не затрагивают дифф из восьми файлов и не блокируют merge данной задачи.

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

### 2026-08-08 — Implement: доказан старый статус 15 падений Vitest
По решению владельца перед merge требовалось доказать, что 15 падений полного Vitest — не поломка ветки. Установлены зависимости и прогнан `npx vitest run` на чистом `origin/main` (9e46f22, отдельный git worktree в `/tmp/main-check`): та же поставка — Test Files 1 failed | 5 passed, Tests 15 failed | 67 passed, все 15 в неизменённом `src/App.test.tsx`. Список названий упавших тестов на ветке (69/84) и на main (67/82) сверен построчно — совпадает побайтово (разница только в 2 добавленных Settings-тестах). Значит поломка старая, не от этой ветки; merge разрешён без дополнительной починки.
Отдельная задача: завести починку `web/src/App.test.tsx` (15 падений, судя по названиям тестов — устаревшие ожидания после переработки экрана «Работа»/навигации) как самостоятельный тикет вне этого пайплайна.

### 2026-08-08 — Чистая поставка русских названий и подсказок Settings
Ветка `factory/bf4e3ba5-e10-5789a27b-505` смешивала перевод Settings с несвязанными файлами (Overview, Summary, pilot.py, CARD-0032); по решению владельца собрана узкая ветка `factory/b996395e-1f0-d4c22b55-af4` от свежего `origin/main`: точечно перенесены только `web/src/Settings.tsx`, `web/src/Settings.test.tsx`, `web/e2e/control-plane.spec.ts`, `web/e2e/server.mjs`, `internal/controlplane/pilot_config_test.go` и пересобран `web/dist`. Так как на `main` уже жила отдельная фича «группы уведомлений на телефон» (коммит `db4935b`), файлы не копировались вслепую — перевод и подсказки объединены вручную поверх текущего Settings.tsx, фича групп уведомлений сохранена и тоже получила подсказки под каждым переключателем.
Правка `pilot_config_test.go` и `web/e2e/server.mjs` не про перевод сам по себе, а чинит рассинхронизацию формата `stages` (map → list), из-за которой `go vet ./internal/controlplane/...` не собирался на чистом `origin/main` — без неё `go test ./...` не запускается вовсе.
Доказательство: `npm run typecheck`, `npm run build`, `go build ./...`, `go vet ./internal/controlplane/...`, `go test ./internal/controlplane/... -run TestPilotConfig` (3/3), `npx vitest run src/Settings.test.tsx` (6/6), `npx eslint src/Settings.tsx src/Settings.test.tsx` (чисто); `git diff --name-only origin/main` показывает только восемь файлов задачи.
Открытый риск (по решению владельца — не трогать в этой задаче): полный `npm run lint` даёт 10 ошибок вне Settings (`Pipeline.tsx`, `Say.tsx` — `react-hooks/set-state-in-effect`, неиспользуемые `e`, доступ к ref во время рендера); полный `npx vitest run` даёт те же 15 старых падений в неизменённом `App.test.tsx`; `go test ./...` падает на неизменённом `TestHTTPManagedRepositoryCatalog` (404 вместо 200). Разобрать отдельной задачей.

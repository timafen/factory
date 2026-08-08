# Infrastructure findings backlog

### 2026-08-08 — Экран настроек pilot
На ветке `factory/ddaa8de1-fa2-66c96daa-db5` (проверенный HEAD `b279e48`) добавлены безопасный API и `/settings` для `pilot/config.json`.
Список worker ID впервые берётся из уже известных control-plane исполнителей и дальше хранится в настройках; default остаётся `allow_any_worker=true`.
Доказательство: `go test ./...`, `npm test`, `npm run lint`, `npm run build` (результаты зафиксированы в delivery report).
Открытый риск: pilot не участвует в общем межпроцессном lock; конфликт API определяется по версии непосредственно перед atomic replace.

## HEAD
- Status: READY — ветка пересобрана от актуального `origin/main`, поставка экрана «Обзор» проверена.
- Branch: `factory/2ea139c6-a73-e5b02bb1-28d`.
- Head commit: `7dd226c` (фактическая вершина перед этой итоговой записью).
- What changed: активная работа показывает название, постановщика и локализованный этап; некорректный JSON `/works` явно помечает метаданные неполными.
- Evidence: Go target PASS; Overview Vitest 5/5 PASS; changed-files ESLint PASS; typecheck/build PASS; diff содержит ровно 7 файлов: `dashboard_http.go`, `dashboard_http_test.go`, CARD-0030, `web/dist/index.html`, один bundle, `Overview.tsx`, `Overview.test.tsx`.
- One next action: проверить чистую поставку и влить её в `main`.

## LOG

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

### 2026-08-08 — Implement

Изменение экрана «Обзор» перенесено на чистую ветку от свежего `main`: в поставке остались только серверный счётчик, UI, тесты, собранный bundle и эта карточка. Ошибка `json()` ответа `/works` теперь выставляет предупреждение о неполных метаданных; сценарий закреплён отдельным Vitest-тестом. Точечные Go/Vitest/ESLint, TypeScript и production build прошли; полные проверки сохраняют известные несвязанные сбои свежего `main` (catalog route, старые UI-ожидания и lint других экранов).

### 2026-08-08 — Implement

Ветка повторно собрана поверх актуального `origin/main` переносом двух коммитов задачи. Diff подтверждает ровно 7 файлов задачи; целевые Go/Vitest/ESLint, TypeScript, Go build и production build прошли. Полные наборы воспроизводят только базовые сбои в неизменённых `TestHTTPManagedRepositoryCatalog`, `App.test.tsx` и lint других экранов.

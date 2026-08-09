# CARD-0034 — Диалог с мозгом фабрики на выбранной модели

## HEAD

- Status: BLOCKED: полный Vitest-набор имеет 4 падения вне области диалога.
- Branch: `factory/c7d42304-437-ac09919f-7e3`.
- Head commit: `1562fc5` (перебазированная поставка перед записью проверки).
- Evidence: после перебазирования `go test ./...` — PASS; `TestDialog` — PASS;
  TypeScript, production build и 3 сценария Vitest Dialog — PASS. Полный Vitest
  выявил 4 несвязанных падения в Overview, Settings и App.
- One next action: устранить либо подтвердить базовые падения Overview, Settings
  и App, затем повторить полный Vitest-набор.

## LOG

### 2026-08-08 — Specification

Исследованы реальные маршруты `web/src/App.tsx`, API в
`internal/controlplane/http.go`, настройки `brain_chain` и действующий запуск
мозга в `pilot/pilot.py`. Зафиксирован минимальный сквозной контракт экрана,
серверная allowlist выбранной модели и тестируемые обещания реализации.

### 2026-08-08 — Implement

Добавлены экран `/dialog`, история разговора в браузере, серверная allowlist
модели и безопасные runner-контракты для `codex` и `claude`. Целевые Go-тесты
прошли, оба Vitest-сценария прошли, TypeScript и production build собраны.

### 2026-08-08 — Implement (поставка на назначенную ветку)

Реализация перенесена с ветки `factory/0b5a57c8-c65-bded25a5-29d` на назначенную
`factory/176375c6-c70-02958ebc-4e8` (та же ветка уже была перебазирована на
свежий main, ребейз не требовался). Код и код диалога — не отклонение от
области, а обещанные в спецификации `ГОТОВО-КОГДА` файлы. Повторно прогнаны:
`go test ./internal/controlplane -run TestDialog` — PASS; `npx vitest run
src/Dialog.test.tsx` — 2 PASS; `npx tsc --noEmit` и `npx vite build` — PASS;
`go build ./...` и `go test ./...` — PASS кроме заранее известного
`TestHTTPManagedRepositoryCatalog`, который падает так же и на чистом
`origin/main` (проверено в отдельном worktree) — не связан с диалогом.

### 2026-08-08 — Implement (блокеры ревью)

Выбор модели переведён с неоднозначного имени на индекс конкретной строки
`brain_chain`; ответы CLI о rate limit распознаются как HTTP 429 и объясняются
по-русски с предложением выбрать другую модель. `go test
./internal/controlplane -run TestDialog -count=1` — PASS; Vitest — 3 PASS;
TypeScript и production build — PASS. Полный `go test ./...` имеет только
известное падение `TestHTTPManagedRepositoryCatalog`, зафиксированное выше.

### 2026-08-08 — Implement (таймаут длинного ответа)

Проверенный HEAD предыдущей поставки исправлен на `b4a9694`. Сервер теперь даёт
60 секунд на запись ответа при 45-секундном лимите диалога; тест запрещает
снова сделать серверный таймаут короче. Целевой тест, тесты диалога,
`go build ./...`, Vitest и web build прошли. Полный пакет controlplane сохраняет
ранее известное падение `TestHTTPManagedRepositoryCatalog`.

### 2026-08-08 — Implement (полный бюджет HTTP)

После замечания ревью `WriteTimeout` увеличен до 90 секунд, а контрактный тест
фиксирует полный бюджет: чтение запроса + лимит диалога + запас. Живой тест
на настоящем HTTP-сервере получил ответ `/dialog` через 16 секунд. Полный
`go test ./...`, три теста Dialog, web build и целевой lint прошли. Полный
Vitest сохраняет несвязанные падения старых тестов настроек, присутствующие
вне области этого узкого исправления.

### 2026-08-09 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Модели и выбор | `npx vitest run src/Dialog.test.tsx` | PASS: первая модель, выбор второй и история в порядке проверены (3/3). |
| Безопасный запрос | `go test ./internal/controlplane -run TestDialog -count=1` | PASS: allowlist, роли, лимиты, таймаут и безопасные ошибки покрыты. |
| Сборка интерфейса | `npx tsc -p tsconfig.app.json --noEmit && npx vite build` | PASS. |
| Полный Go-набор | `go test ./...` после rebase на `origin/main` | PASS. |
| Полный web-набор | `npx vitest run` | 97/101 PASS; 4 падения: Overview (1), Settings (1), App (2), вне файлов диалога. |

Дифф `origin/main...HEAD` содержит только заявленные файлы поставки и карточку;
рабочее дерево очищено от результатов production build. Миграций и ручных шагов
нет. Внешний proxy может иметь собственный timeout, который не задаётся в этом
репозитории.

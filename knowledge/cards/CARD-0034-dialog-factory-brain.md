# CARD-0034 — Диалог с мозгом фабрики на выбранной модели

## HEAD

- Status: Implement + Test — блокеры ревью устранены, целевые проверки зелёные.
- Branch: `factory/b331cb36-760-3b73ea2b-615`.
- Head commit: `d912004`.
- What changed: `/dialog` однозначно выбирает конкретную строку `brain_chain`,
  даже если имена моделей совпадают; лимит провайдера показан отдельной ошибкой.
- Evidence: `go test ./internal/controlplane -run TestDialog` — PASS;
  `npm --prefix web test -- --run src/Dialog.test.tsx` — 3 PASS;
  typecheck и Vite build — PASS.
- One next action: открыть `/dialog` в среде владельца и проверить реальный ответ
  доступной CLI-модели.

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

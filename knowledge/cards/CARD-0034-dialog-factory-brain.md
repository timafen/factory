# CARD-0034 — Диалог с мозгом фабрики на выбранной модели

## HEAD

- Status: Implement + Test — блокер таймаута устранён, проверки зелёные.
- Branch: `factory/dba823a7-502-a344208c-6e1`.
- Head commit: `be6fa62` (исправление выполнено поверх проверенного `b4a9694`).
- What changed: `WriteTimeout` сервера поднят до 60 секунд при лимите диалога
  45 секунд; допустимое соотношение закреплено регрессионным тестом.
- Evidence: целевой тест контракта и тесты диалога — PASS;
  `go build ./...`, Vitest (3 теста) и web build — PASS.
- One next action: вручную проверить на `/dialog` живой ответ модели дольше
  15 секунд.

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

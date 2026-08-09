# CARD-0034 — Диалог с мозгом фабрики на выбранной модели

## HEAD

- Status: Implement + Test — экран и безопасный API реализованы.
- Branch: `factory/0b5a57c8-c65-bded25a5-29d`.
- Head commit: `e5a211a`.
- What changed: `/dialog` ведёт многоходовый разговор с явно выбранной моделью
  из `brain_chain`; сервер ограничивает историю и запускает только известные CLI.
- Evidence: `go test ./internal/controlplane -run TestDialog` — PASS;
  `npx vitest run src/Dialog.test.tsx` — 2 PASS; typecheck и Vite build — PASS.
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

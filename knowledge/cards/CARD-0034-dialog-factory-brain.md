# CARD-0034 — Диалог с мозгом фабрики на выбранной модели

## HEAD

- Status: Specification — ожидает реализации после согласования границ MVP.
- Branch: `factory/f0fef6cf-fcb-00185f64-fbc`.
- What changes: новый экран `/dialog` ведёт многоходовый разговор с явно
  выбранной моделью из `brain_chain`; история MVP хранится только в браузере.
- Evidence: продуктовый и технический контракт, критерии и красная целевая
  команда записаны в `knowledge/specs/dialog-factory-brain-selected-model.md`.
- One next action: согласовать неперсистентную историю и отсутствие fallback,
  затем реализовать спецификацию.

## LOG

### 2026-08-08 — Specification

Исследованы реальные маршруты `web/src/App.tsx`, API в
`internal/controlplane/http.go`, настройки `brain_chain` и действующий запуск
мозга в `pilot/pilot.py`. Зафиксирован минимальный сквозной контракт экрана,
серверная allowlist выбранной модели и тестируемые обещания реализации.

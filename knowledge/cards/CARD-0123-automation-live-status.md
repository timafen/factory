Implementation commit: 61e6aa4335024c7bcc45268cb05731e2ad656635 — единый живой статус control-plane и host-автоматик на экране «Автоматизация»

# CARD-0123 — Живой статус всех автоматик Фабрики

## HEAD

Status: Implemented

Branch: `factory/a80d06c8-2f1-584ce472-4a9`

Implementation commit: `61e6aa4335024c7bcc45268cb05731e2ad656635`

What changed: pilot атомарно сохраняет минимальный allowlist-снимок host-служб. Новый read-only endpoint объединяет его с durable Automation, а `/automations` показывает назначение, состояние и последнюю активность каждой строки, сохраняя `no_data` при отказах.

Evidence: `go test ./internal/controlplane -run 'TestAutomationStatus'` → PASS; `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests` → PASS; `npm --prefix web test -- --run src/App.test.tsx` → PASS; typecheck, lint и build → PASS.

One next action: проверить `/automations` на стенде после доставки snapshot обновлённым pilot.

## LOG

### 2026-08-13 — Implement

Добавлены нормализованная модель и endpoint статусов, безопасная host-инвентаризация pilot и единый экран с видимыми состояниями control plane, pilot, release broker, release-службы и janitor. Частичный отказ проверен как сохранённая строка `no_data`; существующий detail доступен только durable Automation.

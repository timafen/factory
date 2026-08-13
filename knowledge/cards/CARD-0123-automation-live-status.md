Implementation commit: 54b9a2fa31b097579bee1dfb49d5eb3e4c2a2a4e — единый живой статус control-plane и host-автоматик на экране «Автоматизация»

# CARD-0123 — Живой статус всех автоматик Фабрики

## HEAD

Status: Implemented

Branch: `factory/a80d06c8-2f1-584ce472-4a9`

Implementation commit: `54b9a2fa31b097579bee1dfb49d5eb3e4c2a2a4e`

What changed: pilot атомарно сохраняет минимальный allowlist-снимок host-служб. Новый read-only endpoint объединяет его с durable Automation, а `/automations` показывает назначение, состояние и последнюю активность каждой строки, сохраняя `no_data` при отказах.

Evidence: `go test ./...` → PASS; Python snapshot → 1 PASS; Vitest → 15 files / 174 tests PASS; typecheck, lint и production build → PASS.

One next action: проверить `/automations` на стенде после доставки snapshot обновлённым pilot.

## LOG

### 2026-08-13 — Implement

Добавлены нормализованная модель и endpoint статусов, безопасная host-инвентаризация pilot и единый экран с видимыми состояниями control plane, pilot, release broker, release-службы и janitor. Частичный отказ проверен как сохранённая строка `no_data`; существующий detail доступен только durable Automation.

Полная проверка после интеграции: все Go-пакеты и 174 UI-теста прошли; production build собран.

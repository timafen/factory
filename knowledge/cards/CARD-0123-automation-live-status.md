Implementation commit: 9069ceea24a6a2ff49e19ad8f52d37ced07fd048 — достоверный живой статус автоматик с TTL snapshot и временем завершённого цикла

# CARD-0123 — Живой статус всех автоматик Фабрики

## HEAD

Status: Implemented

Branch: `factory/432f3286-d0e-16b8bc6e-399`

Implementation commit: `9069ceea24a6a2ff49e19ad8f52d37ced07fd048`

What changed: snapshot host-служб содержит `observed_at` и становится `no_data` через пять минут. Endpoint и pilot используют единый `FACTORY_DATA_HOME` с fallback `/opt/factory-data`; pilot записывает реальное окончание цикла, а systemd-время переводит в UTC.

Evidence: `go test ./internal/controlplane -run 'TestAutomationStatus'` → PASS; `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests` → 2 PASS; `go test ./...`, `npm run typecheck`, `npm run build` → PASS.

One next action: выполнить Review и Verify, включая визуальную проверку `/automations` на стенде.

## LOG

### 2026-08-13 — Implement

Добавлены нормализованная модель и endpoint статусов, безопасная host-инвентаризация pilot и единый экран с видимыми состояниями control plane, pilot, release broker, release-службы и janitor. Частичный отказ проверен как сохранённая строка `no_data`; существующий detail доступен только durable Automation.

Полная проверка после интеграции: все Go-пакеты и 174 UI-теста прошли; production build собран.

### 2026-08-13 — Implement

Исправлена достоверность live-статусов после замечаний Review: просроченный или лишённый `observed_at` snapshot больше не выглядит работающим; data root control plane совпадает с pilot. Для pilot сохраняется время успешно завершённого цикла, а systemd timestamp с локальной зоной переводится в UTC.

Проверено: `go test ./internal/controlplane -run 'TestAutomationStatus'`, `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests`, `go test ./...`, `npm run typecheck` и `npm run build` прошли.

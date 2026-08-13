Implementation commit: 22beed76b64dcab5614dc6a6a6bf9b6a312145fc — защита живого статуса от невалидных и будущих данных

# CARD-0123 — Живой статус всех автоматик Фабрики

## HEAD

Status: Implemented — awaiting Review

Branch: `factory/afcd5c56-3af-617a4988-fae`

Implementation commit: `22beed76b64dcab5614dc6a6a6bf9b6a312145fc`

What changed: невалидная календарная дата janitor остаётся `no_data`, а snapshot с будущим `observed_at` не считается живым. На узком экране live-строка сохраняет состояние и последнюю активность.

Evidence: `go test ./...` → PASS; `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests` → 3 PASS; Playwright mobile status scenario → PASS; `npm run typecheck` and `npm run build` → PASS.

One next action: выполнить Review исправлений до перехода к следующему этапу.

## LOG

### 2026-08-13 — Implement

Добавлены нормализованная модель и endpoint статусов, безопасная host-инвентаризация pilot и единый экран с видимыми состояниями control plane, pilot, release broker, release-службы и janitor. Частичный отказ проверен как сохранённая строка `no_data`; существующий detail доступен только durable Automation.

Полная проверка после интеграции: все Go-пакеты и 174 UI-теста прошли; production build собран.

### 2026-08-13 — Implement

Исправлена достоверность live-статусов после замечаний Review: просроченный или лишённый `observed_at` snapshot больше не выглядит работающим; data root control plane совпадает с pilot. Для pilot сохраняется время успешно завершённого цикла, а systemd timestamp с локальной зоной переводится в UTC.

Проверено: `go test ./internal/controlplane -run 'TestAutomationStatus'`, `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests`, `go test ./...`, `npm run typecheck` и `npm run build` прошли.

### 2026-08-13 — Implement

Устранены три блокирующих замечания Review: календарная валидация janitor timestamp, отклонение snapshot из будущего и мобильная разметка live-статуса. Добавлены регрессионные Go, Python и Playwright проверки; полный Go-набор, typecheck и production build прошли.

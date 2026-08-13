Implementation commit: 22beed76b64dcab5614dc6a6a6bf9b6a312145fc — защита живого статуса от невалидных и будущих данных

# CARD-0123 — Живой статус всех автоматик Фабрики

## HEAD

Status: Verified PASS — awaiting human merge

Branch: `factory/afcd5c56-3af-617a4988-fae`

Implementation commit: `22beed76b64dcab5614dc6a6a6bf9b6a312145fc`

What changed: невалидная календарная дата janitor остаётся `no_data`, а snapshot с будущим `observed_at` не считается живым. На узком экране live-строка сохраняет состояние и последнюю активность.

Evidence: pinned base `99701704b37e8740db3fdbe38c0193917570da5c` to candidate `ef15ffde34075907c9894d20209e066b2a80d59e`; `go test -count=1 -timeout 5m ./...` and `go build ./...` → PASS; Python snapshot tests → 3 PASS; UI tests → 15 files / 174 tests PASS; `npm run typecheck`, `npm run build`, and the mobile live-status Playwright scenario → PASS; `git diff --check` → PASS.

One next action: выполнить human merge candidate branch.

## LOG

### 2026-08-13 — Verify

| Acceptance criterion | Проверка | Результат |
|---|---|---|
| Все автоматики видны на экране | `npm test -- --run` | 15 файлов, 174 теста PASS |
| Статус и последняя активность живые и безопасно обрабатываются | `go test -count=1 -timeout 5m ./...`; `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests` | Go suite PASS; 3 Python теста PASS |
| Узкий экран сохраняет live-строку | Playwright `keeps live Automation state and activity visible on a phone` | PASS; screenshot создан |
| Сборка пригодна к публикации | `npm run typecheck`; `npm run build`; `go build ./...` | PASS; только non-blocking warning о размере JS chunk |

Закреплённое сравнение: base `99701704b37e8740db3fdbe38c0193917570da5c`, candidate `ef15ffde34075907c9894d20209e066b2a80d59e`.

### 2026-08-13 — Implement

Добавлены нормализованная модель и endpoint статусов, безопасная host-инвентаризация pilot и единый экран с видимыми состояниями control plane, pilot, release broker, release-службы и janitor. Частичный отказ проверен как сохранённая строка `no_data`; существующий detail доступен только durable Automation.

Полная проверка после интеграции: все Go-пакеты и 174 UI-теста прошли; production build собран.

### 2026-08-13 — Implement

Исправлена достоверность live-статусов после замечаний Review: просроченный или лишённый `observed_at` snapshot больше не выглядит работающим; data root control plane совпадает с pilot. Для pilot сохраняется время успешно завершённого цикла, а systemd timestamp с локальной зоной переводится в UTC.

Проверено: `go test ./internal/controlplane -run 'TestAutomationStatus'`, `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests`, `go test ./...`, `npm run typecheck` и `npm run build` прошли.

### 2026-08-13 — Implement

Устранены три блокирующих замечания Review: календарная валидация janitor timestamp, отклонение snapshot из будущего и мобильная разметка live-статуса. Добавлены регрессионные Go, Python и Playwright проверки; полный Go-набор, typecheck и production build прошли.

Implementation commit: 14ab4d6e23d104673dc4f1238a5ad1c5d5eb064c — экран показывает статусы durable Automation и host-автоматик без ложной активности

# CARD-0123 — Живой статус всех автоматик Фабрики

## HEAD

Status: Implemented — duplicate review closed; already in origin/main

Branch: `main`

What changed: экран объединяет durable Automation, pilot, release broker, release-службы и janitor. Будущие timestamps systemd и janitor отклоняются, поэтому ложной «живой» активности нет.

Evidence: Python snapshot tests → 4 PASS; `go test ./internal/controlplane` и `go build ./...` → PASS; UI → 180 PASS, typecheck, lint и build → PASS.

One next action: Review проверяет каноническую поставку перед merge.

## LOG

### 2026-08-13 — Verify

| Проверка | Команда | Результат |
| --- | --- | --- |
| Полный Go-набор | `go test ./...` | PASS, все пакеты |
| Live-status snapshot | `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests` | PASS, 3/3 |
| Web UI | `cd web && npm test -- --run` | PASS, 174/174 теста |
| Типы, lint, production build | `cd web && npm run typecheck && npm run lint && npm run build` | PASS |
| Pinned поставка | `git diff 99701704b37e8740db3fdbe38c0193917570da5c...e84e8fc7d0a20d0b5d7833c67acf9bd5e23ebdc3` | 19 task-only файлов, посторонних изменений нет |

Экран показывает durable Automation, pilot, release broker, release-службы и janitor с живым статусом и последней активностью; частичный отказ источника сохраняет строку как `no_data`, а действия остаются только у durable Automation.

### 2026-08-13 — Implement

Добавлены нормализованная модель и endpoint статусов, безопасная host-инвентаризация pilot и единый экран с видимыми состояниями control plane, pilot, release broker, release-службы и janitor. Частичный отказ проверен как сохранённая строка `no_data`; существующий detail доступен только durable Automation.

Полная проверка после интеграции: все Go-пакеты и 174 UI-теста прошли; production build собран.

### 2026-08-13 — Implement

Исправлена достоверность live-статусов после замечаний Review: просроченный или лишённый `observed_at` snapshot больше не выглядит работающим; data root control plane совпадает с pilot. Для pilot сохраняется время успешно завершённого цикла, а systemd timestamp с локальной зоной переводится в UTC.

Проверено: `go test ./internal/controlplane -run 'TestAutomationStatus'`, `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests`, `go test ./...`, `npm run typecheck` и `npm run build` прошли.

### 2026-08-13 — Implement

Устранены три блокирующих замечания Review: календарная валидация janitor timestamp, отклонение snapshot из будущего и мобильная разметка live-статуса. Добавлены регрессионные Go, Python и Playwright проверки; полный Go-набор, typecheck и production build прошли.

### 2026-08-13 — Implement

Реализация заново собрана от свежего `origin/main` без посторонних файлов: единый read-only endpoint и экран показывают все штатные автоматики, их назначение, состояние и последнюю активность; ошибки host-источников не скрывают строки и не создают ложное здоровье.

Проверено: `go test ./internal/controlplane -run 'TestAutomationStatus'`, 3 Python snapshot-теста и 64 UI-теста прошли; `go build ./...`, typecheck, lint и production build успешны.

### 2026-08-13 — Implement

Каноническая поставка перенесена на свежий `main`. Будущие timestamps systemd и janitor теперь остаются `no_data`, а не создают ложное впечатление работающей автоматики; добавлен общий регрессионный тест для обоих источников.

Проверено: `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests pilot.test_pilot.AreaLockArbitrationTests` → 7 PASS; `go test ./internal/controlplane` и `go build ./...` → PASS; web UI → 180 PASS, typecheck, lint и build → PASS после `npm ci`.

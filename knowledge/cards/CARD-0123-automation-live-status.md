Implementation commit: f8b5c4dc4c06349fde33468197f77c322c3cc6a6 — единый экран всех автоматик Фабрики с живым безопасным статусом

# CARD-0123 — Живой статус всех автоматик Фабрики

## HEAD

Status: Verified PASS — awaiting human merge

Branch: `factory/0a889f49-635-e5804601-452`

Implementation commit: `f8b5c4dc4c06349fde33468197f77c322c3cc6a6`

What changed: экран объединяет durable Automation, pilot, release broker, release-службы и janitor. Частичный отказ сохраняет строку с честным `no_data`, а действия остаются только у durable Automation.

Evidence: целевой Go-тест → PASS; Python snapshot tests → 3 PASS; UI → 64 PASS; `npm run typecheck`, `npm run lint`, `npm run build` и `go build ./...` → PASS.

One next action: выполнить human merge этой проверенной ветки.

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

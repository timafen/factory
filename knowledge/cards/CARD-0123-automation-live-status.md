Implementation commit: 416ea4082348b1702081e81474bfab72190c3151 — единый экран всех автоматик Фабрики с живым безопасным статусом

# CARD-0123 — Живой статус всех автоматик Фабрики

## HEAD

Status: Implemented and tested — ready for Review

Branch: `factory/7b581b25-e52-d31eb11d-e31`

Implementation commit: `416ea4082348b1702081e81474bfab72190c3151`

What changed: экран объединяет durable Automation, pilot, release broker, release-службы и janitor. Частичный отказ сохраняет строку с честным `no_data`, а действия остаются только у durable Automation.

Evidence: controlplane/protocol Go tests, 3 snapshot tests, 64 UI tests, lint and production build → PASS. Full pilot module retains 4 unrelated polling/provenance failures outside this change.

One next action: провести Review опубликованного кандидата по закреплённому SHA.

## LOG

### 2026-08-13 — Implement

Кандидат заново собран от свежего `origin/main`: перенесены только endpoint, host-snapshot, экран `/automations`, целевые тесты, спецификация и production bundle этой задачи. Коммит реализации: `416ea4082348b1702081e81474bfab72190c3151`.

Проверено: `go test ./internal/controlplane ./internal/protocol`, 3 Python snapshot-теста и 64 UI-теста прошли; `npm run lint` и `npm run build` успешны. Полный `pilot.test_pilot` сохраняет 4 посторонних сбоя в adaptive polling и correction provenance; целевой класс проходит.

### 2026-08-13 — Verify

| Проверка | Команда | Результат |
| --- | --- | --- |
| API и нормализация статусов | `go test -timeout 5m ./...` | PASS для `internal/controlplane`; все категории и `no_data` покрыты, полный набор остановился на нестабильном `internal/worker` вне поставки |
| Снимок host-автоматик | `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests` | PASS, 3/3 |
| UI-строки и «нет данных» | `npm test -- --run src/App.test.tsx -t 'shows every Factory automation category and honest missing data'` | PASS, 1/1 |
| Браузерная проверка | `npx playwright test -g 'keeps live Automation state and activity visible on a phone'` | PASS, 1/1 на реальном сервере |
| Полный набор | `just check`, `npm run test:browser` | есть посторонние падения: SA4000 в `internal/worker/attempt_lifecycle_test.go`, worker timing, Work view e2e; целевой Chromium-сценарий прошёл |

НАХОДКА: общий `npm test` также нестабилен вне экрана автоматик (13 из 158 тестов); целевой UI-тест и production build прошли.

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

Кандидат повторно собран на ветке `factory/b6b5d71f-34b-5db9b6c5-9a2` от свежего `origin/main`; перенесены только endpoint, host-snapshot, экран, тесты и production bundle этой задачи. Коммит реализации: `b793f4c4a2a7e9e2f11009ec445746d063233632`.

Проверено: целевой Go-тест, 3 Python snapshot-теста и 174 UI-теста прошли; typecheck, lint, Go build и production build успешны. Целевой Playwright не запустил Chromium: sandbox helper получил запрет `sudo` из-за `no_new_privileges`.

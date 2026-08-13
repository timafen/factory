# Экран «Автоматизация»: все автоматики Фабрики видны с живым статусом

## Цель и влияние на владельца

На экране `/automations` владелец видит единый честный статус durable Automation, pilot, release broker, служб выката и janitor: название, назначение, состояние и последнюю активность. При недоступном источнике строка не исчезает и не выглядит здоровой — она показывает «нет данных». Это устраняет ручной поиск systemd и журналов и помогает отличить частичный отказ от нормальной работы.

Эта работа является дубликатом уже проверенной CARD-0123. Повторная реализация запрещена: в продукт должна попасть каноническая ветка `factory/0a889f49-635-e5804601-452` штатным squash-merge; выкат живой Фабрики остаётся отдельным действием CARD-0123.

## Технический подход и реальные файлы

Каноническая поставка добавляет нормализованный read-only DTO и endpoint `GET /api/v1/automations/status`; durable данные берутся control plane, а host-снимок атомарно готовит pilot из фиксированного allowlist systemd-служб. Отсутствующие, просроченные или ошибочные данные нормализуются в `no_data`, без команд, секретов, ExecStart или произвольных строк журналов. UI опрашивает этот endpoint в видимой вкладке; detail и действия остаются только у durable Automation.

Реальные файлы поставки: `internal/protocol/types.go`, `internal/controlplane/automation_status.go`, `internal/controlplane/automation_status_test.go`, `internal/controlplane/automations_status_http.go`, `internal/controlplane/http.go`, `pilot/pilot.py`, `pilot/test_pilot.py`, `web/src/types.ts`, `web/src/api.ts`, `web/src/Automations.tsx`, `web/src/App.test.tsx`, `web/src/test/fixtures.ts`, `web/src/styles.css`, `web/e2e/control-plane.spec.ts`, `web/dist/index.html`, `web/dist/assets/index-C5_H42jx.js`, `web/dist/assets/index-DZJznqea.css`.

## Последовательный план

1. Получить свежий remote `main` и каноническую ветку; проверить только трёхточечный diff между их полными SHA.
2. Убедиться, что diff содержит перечисленные файлы реализации и документы CARD-0123, без посторонних изменений.
3. Выполнить штатный squash-merge канонической ветки в свежий `main`; не переносить изменения вручную и не использовать эту ветку-дубликат для продуктового merge.
4. На отдельной стадии выполнить выкат и live-проверку по CARD-0123.

## Критерии приёмки

- `/automations` выводит durable Automation, pilot, release broker, известные release-службы и janitor одной нормализованной выдачей.
- Каждая строка содержит название, назначение, состояние и последнюю активность либо честное «нет данных».
- Ошибка systemd, отсутствующий журнал, невалидная, будущая или просроченная метка не скрывают строку и не переводят её в работающее состояние.
- Durable Automation сохраняет существующий detail и действия; host-строки не получают управляющих действий.
- Новый endpoint не изменяет контракт существующего CRUD `/api/v1/automations` и не раскрывает чувствительные host-данные.

## Тест-план

- Обязательная быстрая регрессия после merge: `go test ./internal/controlplane -run 'TestAutomationStatus'` завершается с кодом 0 и проверяет объединение источников, сортировку и `no_data`.
- `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests` проверяет allowlist, атомарный снимок, timestamp и частичный отказ.
- `cd web && npm test -- --run web/src/Automations.test.tsx` проверяет все категории, «нет данных» и отсутствие actions у host-строки.
- Verify-стадия запускает полный Go-набор, web tests/typecheck/lint/build и открывает `/automations` на стенде после разрешённого выката.

## Риски и решения

| Риск | Решение |
| --- | --- |
| Повторная реализация расходится с проверенным поведением | Закрыть текущую работу дубликатом и вливать только каноническую ветку squash-merge. |
| Снимок host-статуса недоступен | Сохранять строку с `no_data`, не возвращать ложное здоровье и не ломать остальные источники. |
| Host-инвентаризация раскрывает лишнее | Жёсткий allowlist и минимальный DTO без команд, аргументов и текста журналов. |
| Merge сделан от устаревшей базы | Перед merge повторно получить remote default branch и проверить `<base_sha>...<candidate_sha>`. |

## Карточка работы

Карточка текущего дубликата: `knowledge/cards/CARD-0125-automation-live-status-duplicate.md`.

Каноническая карточка реализации: `knowledge/cards/CARD-0123-automation-live-status.md` в ветке `factory/0a889f49-635-e5804601-452`. Эта ветка спецификации не содержит и не создаёт продуктовый код.

ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл internal/controlplane/automation_status.go
ГОТОВО-КОГДА: файл internal/controlplane/automation_status_test.go
ГОТОВО-КОГДА: файл internal/controlplane/automations_status_http.go
ГОТОВО-КОГДА: файл internal/controlplane/http.go
ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл web/src/types.ts
ГОТОВО-КОГДА: файл web/src/api.ts
ГОТОВО-КОГДА: файл web/src/Automations.tsx
ГОТОВО-КОГДА: файл web/src/App.test.tsx
ГОТОВО-КОГДА: файл web/src/test/fixtures.ts
ГОТОВО-КОГДА: файл web/src/styles.css
ГОТОВО-КОГДА: файл web/e2e/control-plane.spec.ts
ГОТОВО-КОГДА: файл web/dist/index.html
ГОТОВО-КОГДА: файл web/dist/assets/index-C5_H42jx.js
ГОТОВО-КОГДА: файл web/dist/assets/index-DZJznqea.css
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run 'TestAutomationStatus'

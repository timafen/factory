## HEAD

Status: Verified PASS — awaiting human merge

Branch: `factory/7f9b8b54-c5e-f1203080-7eb`

Implementation commit: 2854ae093ae0f841f56dba44ec7f940a5eb164f0 — экран объединяет все автоматики Фабрики с живым безопасным статусом

What changed: добавлены нормализованный endpoint статусов, безопасный host-снимок pilot и экран `/automations` с durable Automation, pilot, release broker, release-службами и janitor. Частичный отказ остаётся видимым как `no_data`, действия доступны только durable Automation.

Evidence: полный `go test ./...` → PASS; `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests` → 3 PASS; полный UI-набор → 16 файлов, 180 тестов PASS; `npm run typecheck`, `npm run lint` и `npm run build` → PASS. Полный Python-набор: 257 тестов, 2 failures и 2 errors в не затронутых данной реализацией AdaptivePollingTests и CorrectionProvenanceStormTests.

One next action: выполнить human merge опубликованной ветки.

## LOG

### 2026-08-13 — Implement

Каноническая реализация CARD-0123 перенесена на ветку дубликата штатным cherry-pick с разрешением только конфликтов pinned web bundle и pilot-теста. Целевые Go/Python проверки прошли; UI typecheck и lint прошли. Полный Go-набор и UI/build запущены перед доставкой.

Риск: отдельный тестовый путь `web/src/Automations.test.tsx` отсутствует в поставке; фактический UI-набор запускается через `npm test -- --run`.

### 2026-08-13 — Specification

Status: Specification — duplicate of CARD-0123; product implementation is not copied to this branch.

Canonical implementation: `factory/0a889f49-635-e5804601-452`. Владелец утвердил штатный squash-merge этой уже проверенной ветки в свежий `main` после проверки её diff. Выкат на живую Фабрику — отдельный шаг по CARD-0123.

Следующее действие: человек проверяет состав канонической ветки и выполняет squash-merge, после чего применяется отдельный план выката из CARD-0123.

### 2026-08-13 — Verify

| Критерий | Команда / проверка | Наблюдаемый результат |
| --- | --- | --- |
| Единый read-only endpoint и fallback | `go test ./internal/controlplane -run 'TestAutomationStatus'` | PASS: durable + pilot, broker, release и janitor; неразрешённый unit отсечён, нет snapshot даёт `no_data`. |
| Честный host snapshot при частичном отказе | `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests` | 3 PASS: allowlist, timestamps, атомарная запись и отсутствие ложного running. |
| Экран и polling | `cd web && npm test -- --run` | 16 файлов, 180 тестов PASS; status query опрашивается видимой вкладкой. |
| Сборка UI и артефакты | `npm run typecheck && npm run lint && npm run build` | PASS; `git status --short` в чистой временной копии пуст. |

НАХОДКА: полный `python3 -m unittest -q pilot.test_pilot` завершился с 2 failures и 2 errors (AdaptivePollingTests и CorrectionProvenanceStormTests); новый live-status subset проходит, а падения не относятся к изменённым строкам.

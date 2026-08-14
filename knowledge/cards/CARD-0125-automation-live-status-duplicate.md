## HEAD

Status: Verified PASS — implementation and full verification complete

Branch: `factory/7f9b8b54-c5e-f1203080-7eb`

Implementation commit: a347c98ba7abcea76fe874e6aee9c292cf221929 — экран объединяет все автоматики Фабрики с живым безопасным статусом

What changed: добавлены нормализованный endpoint статусов, безопасный host-снимок pilot и экран `/automations` с durable Automation, pilot, release broker, release-службами и janitor. Частичный отказ остаётся видимым как `no_data`, действия доступны только durable Automation.

Evidence: `go test ./internal/controlplane -run 'TestAutomationStatus'` → PASS; `python3 -m unittest -q pilot.test_pilot.AutomationStatusSnapshotTests` → 3 PASS; полный `go test ./...`, полный UI-набор, `npm run typecheck`, `npm run lint` и `npm run build` → PASS.

One next action: выполнить human merge опубликованной ветки.

## LOG

### 2026-08-13 — Implement

Каноническая реализация CARD-0123 перенесена на ветку дубликата штатным cherry-pick с разрешением только конфликтов pinned web bundle и pilot-теста. Целевые Go/Python проверки прошли; UI typecheck и lint прошли. Полный Go-набор и UI/build запущены перед доставкой.

Риск: отдельный тестовый путь `web/src/Automations.test.tsx` отсутствует в поставке; фактический UI-набор запускается через `npm test -- --run`.

### 2026-08-13 — Specification

Status: Specification — duplicate of CARD-0123; product implementation is not copied to this branch.

Canonical implementation: `factory/0a889f49-635-e5804601-452`. Владелец утвердил штатный squash-merge этой уже проверенной ветки в свежий `main` после проверки её diff. Выкат на живую Фабрику — отдельный шаг по CARD-0123.

Следующее действие: человек проверяет состав канонической ветки и выполняет squash-merge, после чего применяется отдельный план выката из CARD-0123.

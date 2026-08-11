# CARD-0061 — Безопасный шаблон подключения проекта

## HEAD

- Status: IMPLEMENTED — повторная проверка на свежем `origin/main` зелёная.
- Branch: `factory/afffa74e-365-edac8b70-81e`.
Implementation commit: bbeace8aa1cd8cef2a129c2e14b2ba5c3d0c4f79 — реализованы безопасные шаблоны Factory и staging Tarser.
- Specification: `knowledge/specs/secure-project-onboarding-template.md`.
- What changed: сервер принимает только два утверждённых типа, сам выбирает
  группу и фиксированные release/rollback; `/projects` показывает fail-closed
  ворота и только наличие секретов.
- Evidence: `go test ./internal/controlplane -run 'Project|Secret|Adapter' -count=1` → PASS;
  `npm --prefix web test -- --run src/Projects.test.tsx` → 2 PASS;
  `npx tsc -p tsconfig.app.json --noEmit`, vet, lint и Go/Web build → PASS.
- One next action: Verify открывает `/projects` и подтверждает безопасный сценарий владельца.

## LOG

### 2026-08-10 — Specification

Владелец утвердил v1: человекочитаемое имя, репозиторий, основная ветка, тип,
среды с URL и health-check, проверки, идентификаторы операций, имена секретов и
точный allowlist хостов. Staging обязателен; production блокирован до отдельного
подтверждения владельца. Работа допускается лишь после готовности доступа/worker/
секретов и secret-scan, static/typecheck, tests, build на одном SHA. Секреты
остаются в `/etc/factory/projects/<project>/<environment>.env` с `root`, группой
исполнителя и режимом `0640`; значения не выходят из разрешённой операции.

### 2026-08-10 — Implement

Реализованы миграция, API/store, серверные политики для
`factory-single-instance` и `tarser-operations-staging`, безопасный secret
resolver, единый SHA-набор ворот, фиксированные адаптеры с автоматическим
rollback и экран `/projects`. Целевые Go-тесты, 2 Vitest-теста, vet, lint и обе
сборки прошли; production Tarser и универсальные shell/SSH-адаптеры не добавлены.

### 2026-08-10 — Implement

Работа повторно перенесена на свежий `origin/main` без посторонних файлов.
Обязательный TypeScript-check без emit, целевые Go/Vitest-тесты, vet, lint и обе
сборки прошли; SHA реализации подтверждён как предок текущей ветки.

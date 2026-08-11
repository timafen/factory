# CARD-0061 — Безопасный шаблон подключения проекта

## HEAD

- Status: IMPLEMENTED — целевые проверки и сборки зелёные.
- Branch: `factory/718146bb-bd7-872cc553-67c`.
Implementation commit: 82ed942cb86ab6bae9c660748e0f60a6e9e1ec2e — реализованы безопасные шаблоны Factory и staging Tarser.
- Specification: `knowledge/specs/secure-project-onboarding-template.md`.
- What changed: сервер принимает только два утверждённых типа, сам выбирает
  группу и фиксированные release/rollback; `/projects` показывает fail-closed
  ворота и только наличие секретов.
- Evidence: `go test ./internal/controlplane -run 'Project|Secret|Adapter' -count=1` → PASS;
  `npm --prefix web test -- --run src/Projects.test.tsx` → 2 PASS;
  Go/Web build и web lint → PASS.
- One next action: Verify проверяет целевые контракты и живой экран `/projects`.

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

# CARD-0061 — Безопасный шаблон подключения проекта

## HEAD

- Status: IMPLEMENTED — целевые проверки и обе сборки зелёные.
- Branch: `factory/2b4dbde2-7be-4e0c9a76-9da`.
Implementation commit: 904ffa0a804642b5cde31d982e2ee2e81d7e0b4b — завершены безопасные шаблоны Factory и staging Tarser со строгим FQDN и защитой secret-файла от подмены.
- Specification: `knowledge/specs/secure-project-onboarding-template.md`.
- What changed: сервер принимает только два утверждённых типа, сам выбирает
  группу и фиксированные release/rollback; точный allowlist отклоняет локальные
  и некорректные DNS-имена, а secret-файл сверяется после открытия.
- Evidence: `go test ./internal/controlplane -run 'Project|Secret|Adapter' -count=1` → PASS;
  `npm --prefix web test -- --run src/Projects.test.tsx` → 2 PASS;
  `npx tsc -p tsconfig.app.json --noEmit`, vet, lint и Go/Web build → PASS.
- One next action: Review проверяет diff и экран `/projects`.

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

### 2026-08-10 — Implement

После самостоятельной проверки точный allowlist усилен полноценной валидацией
FQDN, а чтение secret-файла защищено от подмены после `Lstat`. Целевые Go-тесты,
2 Vitest-теста, TypeScript-check, Go vet/build и Web lint/build прошли.

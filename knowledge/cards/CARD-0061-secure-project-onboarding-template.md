# CARD-0061 — Безопасный шаблон подключения проекта

## HEAD

- Status: IMPLEMENTED — два security-блокера повторного Review устранены.
- Branch: `factory/a19865f9-450-b71bfaba-455`.
Implementation commit: a1f85be4a53a611947fa3d76a1fe638683a67337 — окружение адаптера изолировано, а готовность подтверждается сервером и живым worker.
- Specification: `knowledge/specs/secure-project-onboarding-template.md`.
- What changed: адаптер получает фиксированное минимальное окружение и только
  разрешённые секреты проекта. Публичная запись gate-results удалена; routing и
  release дополнительно требуют актуальную `ManagedRepositoryReadiness` worker.
- Evidence: `go test ./internal/controlplane -run 'Project|Secret|Adapter|Tarser' -count=1` → PASS;
  три security-регрессии → PASS; `go vet`, Go/Web build и 2 Vitest-теста → PASS.
- One next action: повторно запустить Review исправленных security-блокеров.

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

### 2026-08-10 — Implement

После rebase обзорная и безопасная готовность получили разные Go-типы без
изменения JSON API. Конфликт собранных Web-артефактов разрешён пересборкой;
целевые Go-тесты и 2 Vitest-теста на итоговом дереве прошли.

### 2026-08-11 — Implement

Работа заново собрана на свежем `origin/main`. Tarser больше не сообщает об
откате без доказательства: ошибка выпуска сверяется с прежней целью релиза, а
ошибка health-check вызывает фиксированный rollback и повторное сравнение.
Значения только объявленных секретов передаются environment разрешённого
процесса и не попадают в API/SQLite; целевые Go/Vitest-тесты, vet, typecheck,
lint и обе сборки прошли.

### 2026-08-11 — Implement

Финальная проверка реального интерфейса Tarser выявила несовместимость прямого
`deploy-release` с Git SHA из API. Адаптер переведён на фиксированную серверную
операцию `fx staging release <SHA>`; точные argv, секретное environment и оба
пути подтверждения rollback повторно проверены целевыми Go-тестами, vet и build.

### 2026-08-11 — Implement

Устранены два блокера повторного Review: процессы адаптеров больше не наследуют
окружение control-plane, а клиентский endpoint записи готовности удалён. Сводная
готовность теперь включает фактическую `ManagedRepositoryReadiness` живого worker;
подделка клиентских полей не открывает routing или release. Целевые Go-тесты,
три security-регрессии, vet, Go/Web build и 2 Vitest-теста прошли.

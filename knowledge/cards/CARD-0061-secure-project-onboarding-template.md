# CARD-0061 — Безопасный шаблон подключения проекта

## HEAD

Implementation commit: bdd9f6043bcb269bb1e85d942076a963a43cb54f — безопасный шаблон проекта реализован с восстановимой выдачей credential, сериализацией операций и точным broker-контрактом.
- Status: READY FOR REVIEW — четыре блокера предыдущего Review закрыты кодом и регрессиями.
- Branch: `factory/099422c3-55d-9d724e3f-e45`.
- Specification: `knowledge/specs/secure-project-onboarding-template.md`.
- What changed: credential можно безопасно восстановить после потери ответа/ошибки
  записи; одна среда допускает одну running-операцию с `409`; broker возвращает
  точный исход отката; экран показывает русские названия и подписанные ID.
- Evidence: целевые Go-тесты и 2 Projects Vitest → PASS; `internal/controlplane`
  полностью → PASS (112.725s); vet, Go/Web build, lint и 142 Vitest → PASS.
- One next action: повторить Review четырёх закрытых границ безопасности.

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

### 2026-08-11 — Implement

После решения владельца закрыты все пять замечаний Review. Добавлен рабочий
worker verifier с проверкой существования `MainBranch` и совпадения SHA с её
HEAD; readiness хранит атомарную аттестацию и привязан к конкретному готовому
worker. Health-check принудительно применяет точный `web_hosts`, а отрицательные
branch/SHA/worker/host сценарии остаются fail-closed. Self-release запускается
узким root-посредником `fx` во внешнем systemd unit и восстанавливается при
старте нового server process. Полный пакет control-plane, целевые worker/UI
тесты, vet, lint, TypeScript и обе сборки прошли.

### 2026-08-11 — Implement

Финальная проверка production unit уточнила self-release: `factory-server` имеет
`NoNewPrivileges=true`, поэтому текущий `fx` не способен создать root systemd job
из процесса сервера. Ложный дочерний путь удалён. Control-plane теперь вызывает
только точную внешнюю операцию: Unix socket
`/run/factory/project-release-broker.sock`, `POST /v1/releases` и последующий
`GET /v1/releases/{operation_id}`. Пока root-owned broker не установлен, выпуск
fail-closed с понятной причиной; отрицательный тест подтверждает отсутствие
запуска. Целевые Go-тесты, vet и обе Go-сборки прошли.

### 2026-08-11 — Implement

Работа заново собрана на свежем `origin/main` без файлов прежней ветки вне
области проекта. После решения владельца worker verification получил независимую
аутентификацию: credential выдаётся только при прямой loopback-регистрации,
хранится на worker с режимом `0600`, а control-plane хранит digest и сверяет его
с worker из URL до разбора отчёта. HTTP-регрессии подтверждают, что запрос без
credential и запрос с credential другого worker получают `401` и не меняют
readiness; корректный worker проходит. Полные тесты двух Go-пакетов, vet,
Go/Web build, lint и 2 Vitest-теста прошли.

### 2026-08-11 — Implement

После решения владельца работа снова собрана на свежем `origin/main` и закрывает
все четыре замечания Review. Регрессии подтверждают ротацию credential после
потери ответа и ошибки записи, атомарный `409` без второго запуска адаптера,
точные исходы автоматического отката broker и русские UI-подписи с пояснёнными
техническими ID. Целевые тесты, полный `internal/controlplane`, vet, Go/Web build,
lint и все 142 Vitest прошли. В полном Go-наборе отдельно зафиксированы две
нестабильные worker-проверки вне области проекта: overlap клонирования и timeout
process group; целевые worker-тесты этой задачи прошли.

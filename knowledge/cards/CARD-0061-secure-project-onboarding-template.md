# CARD-0061 — Безопасный шаблон подключения проекта

## HEAD

Implementation commit: 362ee4f04d234e5e1241653ed0400f347f50d916 — безопасный шаблон проекта и защищённая bootstrap-регистрация worker реализованы.
- Status: READY FOR REVIEW — локальный перехват credential закрыт до мутации worker.
- Branch: `factory/2479d1cd-192-3ea71686-f57`.
- Specification: `knowledge/specs/secure-project-onboarding-template.md`.
- What changed: новый worker предъявляет отдельный bootstrap-секрет из файла
  `0600`; существующий регистрируется своим credential, а запрос без обоих
  получает `401` до изменения состояния и не может подделать readiness.
- Evidence: controlplane → PASS; hostile sequence → PASS; worker target → PASS;
  vet, Go/Web build, TypeScript, lint и 2 Projects Vitest → PASS.
- One next action: повторить Review локальной перерегистрации и ротации credential.

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

### 2026-08-11 — Implement

Работа перенесена пофайлово на свежий `origin/main`. Потерянный ответ на принятый
broker POST больше не финализирует выпуск ложным `rollback_failed`: операция
остаётся `running`, запрещает второй release/rollback и завершается только после
точного GET-статуса broker. Последовательность закреплена регрессией; целевые
Go/worker/Vitest-тесты, vet, TypeScript, lint и обе сборки прошли.

### 2026-08-11 — Implement

После решения владельца закрыт блокер локального перехвата worker credential.
Первичная регистрация требует отдельный серверный bootstrap-секрет в файле
`0600`, а повторная — credential самого worker; обе проверки происходят до
мутации. Hostile-регрессия подтверждает `401`, сохранность исходного credential
и закрытый readiness. Controlplane, целевые worker/security-тесты, vet, обе
Go-сборки, TypeScript, lint, Web build и 2 Projects Vitest прошли. Известный
нестабильный overlap-тест worker один раз упал в пакетном прогоне и прошёл отдельно.

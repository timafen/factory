Implementation commit: 36f2323a9ec2dace4fed2938e838fe38d1b99374 — административные вопросы сначала получает старшая модель, а опасные действия эскалируются владельцу.

# CARD-0133 — Административные вопросы сначала решает старшая модель

## HEAD

- Статус: Implemented and targeted/full tests PASS — candidate published for Review.
- Ветка: `factory/46d7ccaa-669-39c2534f-e2e`.
- Implementation commit: `36f2323a9ec2dace4fed2938e838fe38d1b99374` — admin-вопросы направляются старшей модели до владельца.
- Изменено: безопасные staging-действия проходят через фиксированный `fx` argv; запрещённые и неуспешные действия эскалируются владельцу, служебный аудит скрыт из owner API.
- Evidence: `AdminQuestionRoutingTests` — 10/10 PASS; Pilot 275/275, Go tests/build — PASS.
- Следующее действие: Review проверяет опубликованный candidate относительно свежего remote `main`.

## LOG

### 2026-08-13 — Implement

После замечания Review admin-вопрос теперь записывается с `authority` до запуска
`fx`, поэтому owner API не видит служебную запись. Сохранение через блокировку
сливает уже записанный ответ владельца, а Python и HTTP тесты покрывают окно гонки.

### 2026-08-13 — Implement

Готовая поставка CARD-0116 штатно перенесена одним squash-коммитом на свежий
`origin/main`. Старшая модель выполняет только allowlist-проверки staging, затем
получает результат для решения; владелец видит только явные эскалации. Целевые
Go- и Python-тесты прошли, проверка пробелов diff также успешна.

### 2026-08-13 — Implement

После замечаний Review восстановлено ограничение обычных loop-rescue: ответы
старшей модели больше не продлевают цикл после `max_loop_rescues`, но отдельный
разрешённый `admin_action` по-прежнему проходит через `fx`. Ошибка `fx` теперь
передаётся старшей модели с запретом нового `admin_action`, сохраняется в аудите
и эскалируется владельцу. Проверено 32 целевыми Python-тестами и
`go test ./internal/controlplane`; код-коммит — `b7ac7e202a7427ea82a6fe16404650faffc75a3d`.
Дубликат CARD-0116 удалён, а спецификация теперь ссылается на эту карточку.

### 2026-08-13 — Verify

Pinned сравнение от удалённой базы `ca4f0e35073e1e8a647c2b35ceecd42f8a9f12f5`
до кандидата `c9696b67708057fcd5074333e41d79bbbed61a6d` содержит только шесть
ожидаемых файлов и проходит `git diff --check`. `go test ./...` и `go build ./...`
зелёные; полный Pilot завершился 267 тестами с двумя прежними
restart/provenance-сбоями вне admin-маршрута; web test/typecheck/lint/build
заблокированы отсутствующими инструментами. Целевые 32 Python-теста и HTTP
проверка проходят.

### 2026-08-13 — Implement

После обязательного rebase на свежую удалённую базу
`3c081e3d5cf49765114b5c19213b459514759cb6` код-коммит реализации получил новый
полный SHA `0fbbc0f6e4150d1b29f152b39b512700c50da353`; изменения области задачи
не конфликтовали с независимой правкой systemd. Повторный целевой прогон на
перебазированной ветке: 32 Python-теста → PASS.

### 2026-08-13 — Implement

После ответа владельца restart/provenance-фикстура получила закреплённый SHA
кандидата Verify и перестала зависеть от несуществующей удалённой тестовой
ветки; исправление теста — `de3769ba4532d0a63ce7e88ca6615e58b1a7c472`.
Штатные web-инструменты восстановлены командой `npm ci`. Полный Verify прошёл:
Pilot 267/267 (13 skipped), web 179/179 вместе с typecheck/lint/build,
`go test ./...`, `go build ./...` и `git diff --check` — PASS.

### 2026-08-13 — Implement

После финального rebase на `origin/main` (`14ab4d6e23d104673dc4f1238a5ad1c5d5eb064c`)
implementation commit получил SHA `6e819132b570dcd71c1b6618d6937ba0294b1cb9`,
а исправление restart/provenance-фикстуры —
`6eb0e4771ca3eedc76301f1795f24dea9fd2ec4b`. Rebase прошёл без конфликтов;
полный Verify повторён на свежей базе из-за пересечения изменений Pilot и web.
Новые тесты адаптивного polling выявили двойное чтение часов в одном цикле;
коммит `ea24abb2fea481ba02b8a721903ef7302ceb2f7b` передаёт один timestamp в
automation status и polling hint. Итоговый Verify: Pilot 271/271 (13 skipped),
web 180/180 плюс typecheck/lint/build, полные Go-тесты и сборка — PASS.

### 2026-08-13 — Verify

Pinned remote-проверка: `refs/heads/main` — SHA
`151429d93310549a1bb04182ab688cc828041ed8`; кандидат после rebase — SHA
`94cfc63e121a9f49d1542349551be3104b1dddc7`. Сравнение содержит только
`internal/controlplane/questions_http.go`, `internal/controlplane/questions_http_test.go`,
`knowledge/cards/CARD-0133-admin-questions-first-to-senior-model.md`,
`knowledge/specs/admin-questions-first-to-senior-model.md`, `pilot/pilot.py` и
`pilot/test_pilot.py`; `git diff --check` → PASS.

| Критерий | Команда / проверка | Наблюдение |
| --- | --- | --- |
| 1. Разрешённый staging-вопрос сначала решает старшая модель и вызывает только фиксированный fx argv | `python3 -m unittest -v pilot.test_pilot.AdminQuestionRoutingTests` | 10/10 PASS; `test_allowed_staging_health...` и обе проверки stage-cap подтверждают `sudo -n /usr/local/bin/fx staging health`. |
| 2. Успешная проверка и ответ модели закрывают вопрос без owner-эскалации | Та же целевая команда | `test_wait_after_successful_admin_action...` и auto-answer сценарий PASS; запись отвечает orchestrator, owner-уведомление не создаётся. |
| 3. Отказ fx, неизвестная операция и запретный scope эскалируются без повторной команды | Та же целевая команда | `test_failed_admin_action...`, `test_forbidden_admin_action...` и секретоподобный ввод PASS; второй admin_action не вызывается, причина сохраняется владельцу. |
| 4. Prod, секреты и необратимые действия не доходят до fx | Та же целевая команда | migrate, sandbox без `--dry-run`, `--force`, prod и logs PASS; `_fixed_command` не вызывается. Разрешённые collectstatic и sandbox dry-run сохраняют точный argv. |
| 5. Старые owner-вопросы работают, admin-аудит скрыт от API, гонка ответа сохранена | `python3 -m unittest pilot.test_pilot` и `go test ./internal/controlplane -run '^TestListQuestionsHidesPythonMockRepresentations$' -count=1` | Python 272/272 (13 skipped), HTTP PASS; admin-запись до эскалации не выдаётся, ответ владельца не перезаписывается. |
| 6. Точный argv и отсутствие вызова для запрещённого входа доказаны тестом | Целевой класс `AdminQuestionRoutingTests` | 10/10 PASS; разрешённые действия вызываются только через `/usr/local/bin/fx`, запрещённые — ноль вызовов. |

Полный прогон выполнен один раз на первоначальном pinned-кандидате
`0501e7e9b315f4bd29c56bd8dc69e9f0b74d8cb0` от базы
`14ab4d6e23d104673dc4f1238a5ad1c5d5eb064c`, до продвижения `main`. После продвижения `main` до
`151429d93310549a1bb04182ab688cc828041ed8` кандидат перебазирован; на нём
повторены только `AdminQuestionRoutingTests` (10/10) и HTTP-регрессия — PASS.
Первоначальный полный прогон подтвердил web 180/180, typecheck/lint/build,
`go test ./...`, worker race, vet, staticcheck, vuln, сборки, release, launcher
и whitespace check.
`just test-tooling` отдельно блокирован унаследованным `FACTORY_BUILD_DIR`, а после
очистки окружения падает на старом ожидании `NoNewPrivileges=true` против текущего
`false` в systemd fixture. Browser suite блокирован `sudo`/Chromium из-за
`no new privileges`; эти файлы и поведение не входят в поставку CARD-0133.

### 2026-08-13 — Implement

Поставка восстановлена от свежего `origin/main` без посторонних файлов.
Разрешённые staging-вопросы сначала обрабатывает старшая модель через
фиксированный `fx` argv; опасные варианты до исполнения эскалируются владельцу.
Целевые `AdminQuestionRoutingTests` (10/10) и HTTP-регрессия прошли.

### 2026-08-13 — Verify

| Критерий | Команда / проверка | Наблюдение |
| --- | --- | --- |
| Разрешённый staging-вопрос первым получает старшая модель с фиксированным argv | `python3 -m unittest -v pilot.test_pilot.AdminQuestionRoutingTests` | 10/10 PASS; разрешённые сценарии вызывают только `sudo -n /usr/local/bin/fx staging ...`. |
| Успех закрывает вопрос без владельца; ошибки и запрещённые действия эскалируются | Тот же тестовый класс | PASS: owner-уведомление отсутствует после успеха, а fx-отказ, неизвестный verb, prod, секреты и необратимые действия не исполняются. |
| Старые owner-вопросы сохранены, служебный аудит скрыт | `go test ./internal/controlplane -run '^TestListQuestionsHidesPythonMockRepresentations$' -count=1` | PASS. |
| Полный штатный набор | `just ui-install && just check` | Go-тесты, vet, vuln, staticcheck, lint, typecheck и 180 UI-тестов PASS; `test-tooling` падает на старом ожидании `NoNewPrivileges=true` для release-broker, хотя закреплённая база уже содержит `false` и `ops/` не входит в diff. |

Pinned diff от удалённой базы `151429d93310549a1bb04182ab688cc828041ed8`
до проверенного кандидата `4c50aa91305641d2c1d97e6a0de625967b4e01b2` содержит шесть
ожидаемых файлов; `git diff --check` проходит. Реализация остаётся в коммите
`9f6631a8b48b39669f18040d0186d5540b0011b5`, который предшествует коммиту карточки
и меняет код вне `knowledge/cards/`.

### 2026-08-13 — Implement

Поставка заново собрана на ветке `factory/32a417bb-fe9-a66e4207-bc2` от свежего
`origin/main`; перенесены только четыре файла реализации/тестов, спецификация и
CARD-0133. Код-коммит — `36f2323a9ec2dace4fed2938e838fe38d1b99374`.
Целевые `AdminQuestionRoutingTests` прошли 10/10, HTTP-регрессия, Python
compilation и Go build также завершились успешно.

### 2026-08-13 — Implement

Заявленный снимок реализации восстановлен и опубликован для повторного Review;
его diff со свежей удалённой базой содержит только шесть файлов CARD-0133.
Целевые проверки прошли: Pilot 10/10, HTTP-регрессия PASS; полный Pilot 275/275,
Go tests и build PASS.

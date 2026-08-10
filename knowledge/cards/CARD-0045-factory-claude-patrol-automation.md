# CARD-0045 — Перенос патруля Claude в Factory Automations

## HEAD

- Status: Verified PASS — ожидает human merge.
- Branch: `factory/0d54e9ac-9f8-4834260e-58b`.
- Head commit: `8168bf9` — проверенный кодовый коммит с атомарной защитой конфигурации патруля.
- What changed: первое provision добавляет инструкции и увеличивает версию Automation через CAS; повторный вызов не меняет версию. Контекст свыше 8 KiB отклоняется до записи.
- Evidence: полный uncached `go test -timeout 5m -count=1 ./...` → PASS; 87 Python-тестов и UI lint/typecheck/build → PASS. Критерии патруля подтверждены `Test.*(Schedule|Patrol)` и UI-сценарием подтверждения provision.
- One next action: выполнить human merge в `main`.

## LOG

### 2026-08-10 — Specification

Владелец определил источник задания: не внешний Claude-патруль, а уже
существующий встроенный пробный патруль. Спецификация переносит его смысл,
не угадывает отсутствующие cron, часовой пояс или дополнительные проверки.

### 2026-08-10 — Implement

Provisioner использует существующую schedule Automation, сохраняет в ней
инструкции патруля и не меняет cron или timezone. Повторный provision не
дублирует контекст, а due-run сохраняется как Occurrence с привязанной Task.
Целевые Go и Python проверки завершились успешно.

### 2026-08-10 — Implement

Добавлен продуктовый provision по явному Automation ID и действие с
подтверждением в панели schedule Automation. Интеграционный тест включает
патруль через HTTP и проводит due schedule через durable Occurrence до Task;
целевые и полные Go/UI/Python проверки, vet и сборка завершились успешно.

### 2026-08-10 — Implement

Первое добавление инструкций патруля теперь атомарно увеличивает версию
Automation через CAS, поэтому устаревшее редактирование после отключения не
может стереть инструкции. Повторный provision сохраняет версию, а итоговый
контекст проверяется на границе 8 KiB до записи. Целевые Go-тесты, сборка,
Go vet, UI typecheck/build и профильные UI/Python тесты завершились успешно.

### 2026-08-10 — Implement

HEAD исправлен по решению владельца: `8168bf9` обозначает проверенный кодовый
слепок, а отдельный коммит с этой записью является служебным и меняет только
CARD-0045. Повторно требуется только Review; разработку и Verify не перезапускать.

### 2026-08-10 — Implement

Ветка пересобрана от свежего `origin/main`, в неё перенесены только 14 файлов
реализации и отдельная CARD-0045. Кодовый коммит `8168bf9` подтверждён как
предок текущего HEAD. Целевые Go-тесты, 87 тестов пилота, 63 UI-теста, Go vet,
Go/UI-сборка и UI lint завершились успешно; следующий шаг — повторный Review.

### 2026-08-10 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Provision использует существующую schedule Automation, не меняет cron/timezone и не дублирует инструкции | `go test ./internal/controlplane -run 'Test.*(Schedule|Patrol)' -count=1` | PASS; проверены включение, версия и повторный provision |
| Запуск сохраняется durable Occurrence с Task | тот же интеграционный HTTP-тест | PASS; due schedule прошёл через Occurrence до Task |
| Нельзя создать расписание неявно, потерять инструкции устаревшим редактированием или переполнить context | тот же набор Patrol-тестов | PASS; ошибки и отсутствие частичной записи проверены |
| В панели есть явное подтверждение provision | `npx vitest run src/App.test.tsx --reporter=dot` | PASS; 34 проверки UI, включая Enable/Confirm pipeline patrol |

Полный uncached `go test -timeout 5m -count=1 ./...` завершился PASS; `python3 -m unittest -v pilot.test_pilot` — 87 PASS; UI lint, typecheck и production build — PASS. `just check` останавливается на уже существующих `staticcheck` в `cards_http.go` и `pilot_config.go`, вне diff. Browser suite остановился в неизменённом диалоге Delegate task: repository option остаётся disabled; до патруля дошёл один PASS, остальные 16 не запускались. Рабочее дерево чисто, `git diff --check` пуст, diff от `origin/main` содержит 15 заявленных файлов.

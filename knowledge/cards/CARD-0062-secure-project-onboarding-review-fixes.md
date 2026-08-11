Implementation commit: fa073ed58bfd02a3c61c7e24fdfad9cfbe28c824 — безопасный шаблон проекта и подтверждённый автоматический откат Factory

# CARD-0062 — Безопасное подключение проекта после Review

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/30d07df8-df2-1dd08155-fd2`.
- Implementation commit: `fa073ed58bfd02a3c61c7e24fdfad9cfbe28c824` —
  безопасный шаблон, root-owned release broker и проверяемый автооткат Factory.
- Specification: `knowledge/specs/secure-project-onboarding-template.md`.
- Production: остаётся заблокированным до отдельного серверного одноразового
  подтверждения владельца; клиентское поле `owner_confirmed` отклоняется.
- Evidence: 14 Go-пакетов, 144 UI-теста, 19 browser E2E,
  worker race, static analysis, tooling/installer и launcher — PASS; UI и три
  Go-бинаря — BUILT; дерево после сборки чистое.
- One next action: владельцу влить ветку в `main`.

## LOG

### 2026-08-11 — Implement

Работа заново собрана на свежем `origin/main` только из файлов безопасного
подключения проекта. Добавлены health-подтверждение self-release и rollback,
проверяемый откат при нездоровом выпуске и строгий запрет клиентского
`owner_confirmed`. Целевые и полные Go/Web-проверки, vet, lint, typecheck и обе
сборки прошли.

### 2026-08-11 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| 1. Полный безопасный шаблон | `go test ./internal/controlplane -run 'Project\|Secret\|Adapter' -count=1` | PASS: обязательные поля, allowlist и идемпотентность проверены |
| 2. Production fail-closed | та же команда, `TestProductionStaysBlockedAndRejectsClientOwnerConfirmation` | PASS: клиентский флаг отклонён, production заблокирован |
| 3. Readiness на одном SHA | та же команда, `TestProjectReadinessRequiresSecretsAndEveryGateOnOneSHA` | PASS: неполная/устаревшая readiness не открывает маршрут |
| 4. Секреты не раскрываются | та же команда, secret/JSON tests | PASS: проверяются имя, владелец и режим; значения не выдаются |
| 5. Фиксированные адаптеры без shell | та же команда, adapter tests | PASS: неизвестный ввод отклонён, argv фиксирован |
| 6. Health и rollback | та же команда, release/rollback tests | PASS: health обязателен, неуспех вызывает проверяемый rollback |
| 7. Credential worker | `go test ./internal/worker -run 'Credential\|Registration\|Verifier' -count=1` и полный Go | PASS: credential сохраняется безопасно и входит в claim; чужой/отсутствующий даёт 401 |
| Projects UI | `npm --prefix web test -- --run src/Projects.test.tsx` | PASS: 1 файл, 2/2 теста |
| Полный набор | `just test`, `just test-worker-race`, `just ui-check`, `just test-browser` | BLOCKED: Go 14 пакетов и Web 142/142 PASS; browser 1 FAIL, 18 не запущены из-за fixture PUT → 401 |
| Сборка и смежные проверки | `just build`, `just ui-build 0`, format, vet, vuln, staticcheck, boundary, tooling, launcher | PASS |

### 2026-08-11 — Implement

Browser fixture получает bootstrap credential из Playwright-конфигурации,
передаёт его в `registerWorker`, сохраняет выданный сервером worker credential
и использует его для защищённого claim. Одиночный browser-сценарий и полный
набор из 19 сценариев прошли; `just check`, обе сборки и worker race также PASS.

### 2026-08-11 — Implement

Все Factory/Tarser release и rollback переведены с дочернего `fx` на отдельный
root-owned broker с четырьмя фиксированными adapter ID и Unix-сокетом для группы
`factory`; реальный клиентский вызов проверен под `NoNewPrivileges`. Экран
выбирает staging по имени, отдельно показывает заблокированный production и
опрашивает итог долговечной операции. Целевые Go/UI-проверки, lint, typecheck,
vet, installer, Node-free tooling и сборки UI/трёх бинарей прошли.

### 2026-08-11 — Implement

Работа заново собрана от свежего `origin/main` без посторонних файлов. Broker
распознаёт код 6 от `fx-factory-release` как выполненный автоматический откат;
control-plane после него обязательно проверяет health и показывает владельцу
понятный успех восстановления либо честный `rollback_failed`. Целевые тесты
обоих исходов, Projects UI и сборки UI/трёх Go-бинарей прошли.

### 2026-08-11 — Verify

| Критерий | Команда / проверка | Наблюдаемый результат |
|---|---|---|
| 1. Полный шаблон | `go test ./internal/controlplane -run 'Project\|Secret\|Adapter' -count=1` | PASS: пакет прошёл, обязательные поля и идемпотентность покрыты |
| 2. Production fail-closed | та же команда: `TestProductionStaysBlockedAndRejectsClientOwnerConfirmation` | PASS: клиентское подтверждение отклонено, production заблокирован |
| 3. Readiness на одном SHA | та же команда: `TestProjectReadinessRequiresSecretsAndEveryGateOnOneSHA` | PASS: неполная и устаревшая readiness закрывает маршрут |
| 4. Секреты не раскрываются | та же команда: secret/JSON/process tests | PASS: наружу выходят только имена; значения доступны только разрешённому процессу |
| 5. Фиксированные адаптеры | та же команда + `go test ./internal/releasebroker` в полном наборе | PASS: unknown/command input отклоняется, argv фиксирован, shell нет |
| 6. Health и rollback | adapter/releasebroker tests в `go test -timeout 5m ./...` | PASS: код 6 принят как auto-rollback только после restored health; иначе `rollback_failed` |
| 7. Credential worker | projects HTTP/worker credential tests в `go test -timeout 5m ./...` | PASS: missing/foreign credential даёт 401 без readiness/claim; proxy-bootstrap запрещён |
| Целевой UI | `npm --prefix web test -- --run src/Projects.test.tsx` | PASS: 1 файл, 3/3 теста |
| Полный и смежный набор | `go clean -testcache`; `just check`; после `just ui-install`: `just ui-check`, `just test-tooling`, `just test-launcher`; `FACTORY_BROWSER_LAUNCHER=<non-root-chrome> just test-browser`; `just test-worker-race` | PASS: Go 14 пакетов, UI 144/144, race/tooling/launcher, browser 19/19; первый `just check` после Go остановился на отсутствующем `eslint`, UI пройден после установки lockfile-зависимостей; managed sudo-launcher запрещён `NoNewPrivileges` |
| Сборка и чистота | `FACTORY_BUILD_DIR=<tmp>/bin just build`; `just ui-build 0`; `git status --porcelain` | PASS: три Go-бинаря и UI собраны; дерево чистое |

Живой откат единственного экземпляра Factory не провоцировался; оба
исхода автоотката покрыты целевыми тестами. После замены бинаря
брокера его нужно явно перезапускать, чтобы новая версия начала работать.

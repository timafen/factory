Implementation commit: fa073ed58bfd02a3c61c7e24fdfad9cfbe28c824 — безопасный шаблон проекта и подтверждённый автоматический откат Factory

# CARD-0062 — Безопасное подключение проекта после Review

## HEAD

- Status: IMPLEMENTED — блокирующее замечание повторного Review исправлено.
- Branch: `factory/30d07df8-df2-1dd08155-fd2`.
- Implementation commit: `fa073ed58bfd02a3c61c7e24fdfad9cfbe28c824` —
  безопасный шаблон, root-owned release broker и проверяемый автооткат Factory.
- Specification: `knowledge/specs/secure-project-onboarding-template.md`.
- Production: остаётся заблокированным до отдельного серверного одноразового
  подтверждения владельца; клиентское поле `owner_confirmed` отклоняется.
- Evidence: Factory exit code 6 + restored/failed health → 3/3 PASS;
  releasebroker/control-plane packages → PASS; Projects UI → 3/3 PASS;
  UI и три Go-бинаря → BUILT.
- One next action: повторить Review блокирующего rollback-пути.

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

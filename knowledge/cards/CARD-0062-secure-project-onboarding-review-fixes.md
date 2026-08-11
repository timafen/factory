Implementation commit: c9fe387f4b10d5c92d16b071436690324de35ffc — безопасный шаблон проекта, health-подтверждение выпуска и отката, fail-closed production

# CARD-0062 — Безопасное подключение проекта после Review

## HEAD

- Status: BLOCKED — обязательный browser-suite падает на регистрации fixture-worker
  без нового server-issued credential; 18 соседних сценариев не запускаются.
- Branch: `factory/3354b83b-9a8-5c609a06-20e`.
- Implementation commit: `c9fe387f4b10d5c92d16b071436690324de35ffc` —
  безопасный шаблон проекта, fail-closed production, credential worker и
  health-подтверждение выпуска/отката.
- Specification: `knowledge/specs/secure-project-onboarding-template.md`.
- Production: остаётся заблокированным до отдельного серверного одноразового
  подтверждения владельца; клиентское поле `owner_confirmed` отклоняется.
- Evidence: целевые control-plane/worker → PASS; Projects UI → 2/2 PASS;
  полный Go → 14 пакетов PASS; Web unit → 14 файлов, 142/142 PASS; обе сборки,
  vet, vuln, staticcheck, race, tooling и launcher → PASS; browser → FAIL.
- One next action: передавать credential в browser fixture `registerWorker`, затем
  повторить полный browser-suite на исправленном кодовом коммите.

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

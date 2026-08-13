# CARD-0115 — Тестовый host-лимит разблокирует проверки воркера

Implementation commit: 5d471f680c42f1974cdc1bb84e99efcbd3a5fb11 — тестовые Store получили явный host-лимит без изменения production-предела

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/848e71d0-2e6-35042efc-37d`.
- Implementation commit: `5d471f680c42f1974cdc1bb84e99efcbd3a5fb11`.
- What changed: test-only открытие Store принимает положительный лимит; тесты
  пула и reconciliation задают соответственно 10 и `len(cases)` слотов.
- Production truth: обычный `Open` по-прежнему использует `runtime.NumCPU()`;
  логика `Claim` не менялась.
- Evidence summary: `go build ./...` и полный uncached-набор — PASS;
  production-default и оба ранее падавших worker-сценария отдельно — PASS.
- Next action: влить ветку в `main` и возобновить выпускной конвейер.

## LOG

### 2026-08-13 — Implement

Добавлен валидируемый test-only конструктор control plane Store. Fixture пула
сохраняет десять одновременных попыток, а startup reconciliation — все 11
сценариев, независимо от числа CPU test host. Объединённая обязательная команда,
оба отдельных регрессионных запуска и полный uncached Go-набор завершились с
кодом 0; test-only API встречается только в реализации и `*_test.go`.

### 2026-08-13 — Verify

| Критерий | Команда / проверка | Результат |
|---|---|---|
| Полная сборка и тесты проходят | `go build ./...`; `go test -count=1 ./...` | PASS; `internal/controlplane` 128.663s, `internal/worker` 171.610s |
| Production-лимит CPU сохранён, test-only лимит валидируется | `go test -count=1 ./internal/controlplane -run '^TestTestingHostSlotLimitIsExplicitAndProductionDefaultUnchanged$'` | PASS, 0.555s |
| Оба ранее падавших worker-сценария независимы от CPU хоста | `go test -count=1 ./internal/worker -run '^(TestStartupReconciliationClassifiesManifestAndFilesystemState|TestCodexWorkerPoolRunsTenAttemptsAndRefillsReleasedSlot)$'` | PASS, 11.533s |
| Поставка чиста и закреплена | `git diff --check 9af274d80462f6b10c4a95392a65e5022795a2e7...a2001f0f24817dccaf077cc16c0264d5a6cb2519` | PASS; пробельных ошибок нет |

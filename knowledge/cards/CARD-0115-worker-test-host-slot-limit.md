# CARD-0115 — Тестовый host-лимит разблокирует проверки воркера

Implementation commit: 5d471f680c42f1974cdc1bb84e99efcbd3a5fb11 — тестовые Store получили явный host-лимит без изменения production-предела

## HEAD

- Status: Implemented and tested.
- Branch: `factory/848e71d0-2e6-35042efc-37d`.
- Implementation commit: `5d471f680c42f1974cdc1bb84e99efcbd3a5fb11`.
- What changed: test-only открытие Store принимает положительный лимит; тесты
  пула и reconciliation задают соответственно 10 и `len(cases)` слотов.
- Production truth: обычный `Open` по-прежнему использует `runtime.NumCPU()`;
  логика `Claim` не менялась.
- Evidence: три целевых теста — PASS; отдельные worker-регрессии — PASS;
  `go test -count=1 ./...` — PASS.
- Next action: влить ветку в `main` и возобновить выпускной конвейер.

## LOG

### 2026-08-13 — Implement

Добавлен валидируемый test-only конструктор control plane Store. Fixture пула
сохраняет десять одновременных попыток, а startup reconciliation — все 11
сценариев, независимо от числа CPU test host. Объединённая обязательная команда,
оба отдельных регрессионных запуска и полный uncached Go-набор завершились с
кодом 0; test-only API встречается только в реализации и `*_test.go`.

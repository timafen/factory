# CARD-0098 — Общий предел worker-слотов по мощности машины

## HEAD

Implementation commit: 7140b35eeca338079ca28d38b831816943630d4f — `Claim` ограничивает суммарные активные lease числом CPU машины

- Status: Implemented and verified.
- Branch: `factory/3556e388-3ae-7bc51285-a31`.
- What changed: control plane атомарно считает непросроченные `preparing` и
  `running` attempts всех worker; после заполнения машинного бюджета новый
  claim возвращается пустым и не создаёт attempt.
- Evidence: обязательный именованный regression — PASS; `go test ./...` —
  PASS; `go build ./...` — PASS; `git diff --check` — PASS.
- One next action: провести review и влить ветку в `main`.

## LOG

### 2026-08-12 — Implement

Добавлена общая проверка слотов в той же SQLite-транзакции, где выдаётся lease.
На машине с 8 CPU две worker-службы с локальной ёмкостью 10 суммарно получают
восемь attempts, а девятый claim остаётся пустым. Интеграционные тесты worker
переведены с жёсткого ожидания десяти одновременных attempts на фактический
машинный бюджет и освобождают lease между независимыми fixture.

Доказательства: именованный regression и два затронутых worker-сценария прошли;
повторный `go test ./... -count=1` прошёл, `go build ./...` завершился без
ошибок. Первый полный прогон выявил старые ожидания десяти слотов; они исправлены
отдельным коммитом до финальной зелёной проверки.

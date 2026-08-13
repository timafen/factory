# CARD-0098 — Общий предел worker-слотов по мощности машины

Implementation commit: 7888a5ed5a6da700e8ef0cccb8aff9ca020abd0b — прямой Store получает безопасный предел worker-слотов.

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/f8b1d7e8-e3c-7b11af26-8a3`.
- Implementation commit: 7888a5ed5a6da700e8ef0cccb8aff9ca020abd0b — прямой Store получает безопасный предел worker-слотов.
- What changed: `Claim` берёт предел из `runtime.NumCPU()`, когда Store создан напрямую без явного лимита; `Open` сохраняет явную инициализацию.
- Evidence: `go test ./...` → PASS; тесты проверяют общий лимит, освобождение слота, replay и конкурентные claim.
- Next action: человек выполняет merge ветки в `main`.

## LOG

### 2026-08-12 — Implement

На одном control plane несколько worker больше не могут суммарно занять слотов,
чем есть логических CPU. Завершённые и истёкшие lease освобождают общий бюджет;
повтор того же запроса возвращает исходную попытку. Документация поясняет, что
локальный `max_concurrent` не отменяет этот фиксированный предел узла.

### 2026-08-12 — Implement

Прямое создание `Store` без `hostMaxConcurrent` больше не блокирует все claim:
нулевое поле получает безопасный предел по числу CPU. Явная инициализация в
`Open` сохранена. Регрессионная проверка и пакет control plane проходят.

### 2026-08-12 — Verify

| Критерий | Проверка | Наблюдаемый результат |
| --- | --- | --- |
| Общий бюджет равен числу логических CPU | `go test ./...` | PASS; `TestClaimEnforcesHostMaxConcurrentAcrossWorkers` занимает ровно `runtime.NumCPU()` попыток между worker и отклоняет следующую. |
| Слот возвращается после завершения или истечения lease | `go test ./...` | PASS; тот же тест получает новую работу после terminal attempt и после истекшего lease. |
| Одновременные claim не переполняют бюджет | `go test ./...` | PASS; `TestConcurrentClaimsDoNotExceedHostCapacity` подтверждает ровно один успешный claim на последнем слоте. |
| Прямой `Store` безопасен | `go test ./...` | PASS; `TestDirectStoreClaimUsesDefaultHostCapacity` проверяет fallback к числу CPU. |

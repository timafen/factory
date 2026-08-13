# CARD-0098 — Общий предел worker-слотов по мощности машины

Implementation commit: 7888a5ed5a6da700e8ef0cccb8aff9ca020abd0b — прямой Store получает безопасный предел worker-слотов.

## HEAD

- Status: Implemented and verified.
- Branch: `factory/f8b1d7e8-e3c-7b11af26-8a3`.
- Implementation commit: 7888a5ed5a6da700e8ef0cccb8aff9ca020abd0b — прямой Store получает безопасный предел worker-слотов.
- What changed: `Claim` берёт предел из `runtime.NumCPU()`, когда Store создан напрямую без явного лимита; `Open` сохраняет явную инициализацию.
- Evidence: `go test ./internal/controlplane -count=1` → PASS, включая проверку claim у прямого Store.
- Next action: передать ветку на повторный review.

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

# CARD-0098 — Общий предел worker-слотов по мощности машины

## HEAD

- Status: Implemented and verified.
- Branch: `factory/5b05f817-fcf-10103e13-c2d`.
- Implementation commit: 60eb87d52fd38c93a168315eefd6508de4f2dda1 — `Claim` ограничивает суммарные active lease числом CPU машины.
- What changed: control plane сохраняет лимит из `runtime.NumCPU()` и атомарно ограничивает все непросроченные `preparing` и `running` attempts.
- Evidence: `go test ./internal/controlplane -count=1` → PASS; целевые проверки предела, replay, освобождения lease и гонки за последний слот → PASS.
- Next action: передать ветку на review.

## LOG

### 2026-08-12 — Implement

На одном control plane несколько worker больше не могут суммарно занять слотов,
чем есть логических CPU. Завершённые и истёкшие lease освобождают общий бюджет;
повтор того же запроса возвращает исходную попытку. Документация поясняет, что
локальный `max_concurrent` не отменяет этот фиксированный предел узла.

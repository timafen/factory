# CARD-0096 — Активные работы не теряют lease синхронной пачкой

Implementation commit: ac824ad5682d53ed50dda1bde05353b29e7d28a9 — повтор heartbeat сохраняет бюджет lease, а пуловый сценарий проверяет десять runtime.

## HEAD

- Status: Implemented — готово к повторному Review.
- Branch: `factory/3c22c13c-edd-30e68460-ff2`.
- Specification: `knowledge/specs/batch-lease-expiry-resilience.md`.
- Owner impact: краткая очередь heartbeat-запросов больше не заставляет worker
  переждать остаток аренды после временной ошибки.
- What changed: повтор renewal ограничивается оставшимся lease-бюджетом; десять
  fake-runtime через Manager/Store подтверждают renewal, отсутствие `lost` и успех.
- Evidence: `go test -count=1 -run 'Test(LeaseRenewalRetry|CodexWorkerPoolRunsTenAttemptsAndRefillsReleasedSlot)$' ./internal/worker` → PASS; `git diff --check` → PASS.
- One next action: повторный Review проверит изменения относительно свежего main.

## LOG

### 2026-08-12 — Implement

На worker добавлен стабильный разброс renewal в диапазоне 70–100% интервала,
ограничение контекста оставшимся lease-бюджетом и обновление supervisor до записи
manifest. Heartbeat control plane теперь меняет только свою attempt; соседние
истёкшие попытки освобождаются штатным sweep. Целевые worker/control-plane тесты,
пачечный integration-сценарий и `git diff --check` прошли.

### 2026-08-12 — Implement

Повтор heartbeat теперь сокращает задержку до остатка lease за вычетом бюджета
следующего запроса, поэтому краткий сбой у deadline не превращается в `lease_lost`.
Интеграционный пул Manager/Store поднимает десять fake-runtime, наблюдает renewal
каждой attempt и подтверждает, что все десять работ завершаются успешно без `lost`.

### 2026-08-12 — Specification

Фактический код показал общий failure mode: все attempt heartbeat-goroutine
используют одинаковые интервалы 10/2 секунды, а каждый renewal выполняет лишнюю
worker-wide capacity reconciliation внутри SQLite write-транзакции. Выбран
совместимый подход: распределить renewals по стабильной фазе, учитывать оставшийся
lease-бюджет и оставить heartbeat только продлением своей attempt. 30-секундный
fail-closed lease, endpoint и operator retry не меняются.

Предыдущая triage-ветка `factory/d3dc8ea2-3bb-cb2b6fde-b96` отсутствовала в
origin на момент Specification; выводы карточки опираются на свежий `origin/main`
и перечисленные регрессионные границы, а не на недоступный diff.

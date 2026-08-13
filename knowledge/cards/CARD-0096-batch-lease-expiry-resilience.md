# CARD-0096 — Активные работы не теряют lease синхронной пачкой

Implementation commit: 5f0ab88e825a32667431e041ade3d262fe23ff25 — lease длится 30 секунд, первый heartbeat планируется через 10 секунд, sweeper запускается каждые 5 секунд.

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/dc529098-99e-a4d9a920-78d`.
- Implementation commit: `5f0ab88e825a32667431e041ade3d262fe23ff25`.
- Specification: `knowledge/specs/batch-lease-expiry-resilience.md`.
- Owner impact: краткая очередь heartbeat-запросов больше не заставляет worker
  переждать остаток аренды после временной ошибки.
- What changed: повтор renewal ограничивается оставшимся lease-бюджетом; десять
  fake-runtime через Manager/Store подтверждают renewal, отсутствие `lost` и успех.
- Evidence: `just build`, `go test -timeout 5m ./...`, целевые lease-тесты, tooling и launcher прошли; закреплённый diff `c28b5bfc...2e86c3d0` содержит только CARD-0096 и чист по `diff --check`. Базовые `staticcheck` SA4000 и UI typecheck остаются вне области поставки.
- One next action: человеку слить карточечную ветку.

## LOG

### 2026-08-12 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Закреплённый состав | `git diff --name-only c28b5bfc...2e86c3d0`; `git diff --check` | PASS: изменена только CARD-0096, whitespace-ошибок нет. |
| Параметры pipeline | константы и запуск целевых Go-тестов | PASS: lease 30 с, первый heartbeat 10 с, sweeper 5 с; worker/control-plane PASS. |
| Сборка | `just build` | PASS: собраны server, worker и release-broker. |
| Полные Go-тесты | `go test -timeout 5m ./...` | PASS: все пакеты прошли. |
| Смежные проверки | `just test-tooling`; `just test-launcher`; `just ui-check`; `staticcheck` | Tooling/launcher PASS; в базе есть UI TS2339 и SA4000 в файлах вне diff. |

### 2026-08-12 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Разнесение renewal | `TestLeaseRenewalScheduleDispersesAttempts` | PASS: десять attempt получают не менее трёх корзин и не выходят за deadline. |
| Пачка из десяти attempts | `TestConcurrentAttemptsStaggerLeaseRenewalsUnderDelay`, `TestCodexWorkerPoolRunsTenAttemptsAndRefillsReleasedSlot` | PASS: renewals распределены, все работы завершаются без `lost`. |
| Retry у deadline | `TestLeaseRenewalRetryStaysWithinLeaseBudget`, `TestLeaseRenewalRetryLeavesTimeForHeartbeatNearExpiry` | PASS: повтор ограничен бюджетом и оставляет время запросу. |
| Изоляция heartbeat | `TestHeartbeatDoesNotReconcileNeighboringExpiredLease` | PASS: соседняя истёкшая attempt завершается только sweep. |
| Совместимость и регрессии | `go test ./...`; `git diff --check` | PASS; миграций и нового endpoint нет. |

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

### 2026-08-12 — Implement

После замечания ревью из поставки удалены `CARD-0107` и лишняя спецификация;
трёхточечный diff оставляет только `knowledge/cards/CARD-0096-batch-lease-expiry-resilience.md`.
Проверено: `git diff --name-only origin/main...HEAD` показывает один файл, `git diff --check` чист.

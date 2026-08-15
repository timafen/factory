# CARD-0092 — Счётчик занятости воркера сам восстанавливается

## HEAD

- Status: Implemented and verified PASS — awaiting repeat Review.
- Branch: `factory/f0c9b344-9dd-7e6b11d4-e7a`.
Implementation commit: b0d8a43f0dcf3d3c836847ee58885f12577dab1d — регрессия подтверждает восстановление двух слотов без двойного запуска supervisor.
- What changed: reconnect-регрессия записывает каждый фактический старт barrier-supervisor и требует ровно один старт для каждой новой попытки.
- Evidence: целевые тесты PASS (controlplane 0.495s, worker 5.207s); polling с таймаутом PASS (1.908s); `go test -timeout 5m ./...` и `just build` PASS.
- One next action: repeat pinned Review against the fresh `origin/main` base.

## LOG

### 2026-08-11 — Implement

После потерянного ответа `/complete` и restart control plane worker снова заполняет
все два слота, но каждая новая barrier-попытка запускает supervisor ровно один раз.
Регрессия сохраняет отдельную запись каждого старта и отвергает повторный запуск для
того же attempt. Целевая интеграционная проверка worker завершилась PASS (8.652s).

### 2026-08-12 — Verify

| Проверка | Команда | Результат |
| --- | --- | --- |
| Восстановление всех слотов и один запуск supervisor на attempt | `go test ./internal/controlplane ./internal/worker -run '^(TestClaimReconcilesStaleCachedCapacityWithoutWorkerRestart|TestReconnectAfterLostCompletionRestoresEveryWorkerSlot)$' -count=1` | PASS; controlplane 0.776s, worker 17.472s |
| Полный набор проекта | `go test ./...` | FAIL только в `TestIdleWorkerMakesOneClaimPerPollingInterval`: timeout 5.84s; остальные пакеты PASS |

### 2026-08-14 — Implement

Изменения перенесены на свежий `origin/main`; кодовый коммит содержит только
интеграционную регрессию. После reconnect воркер заполняет оба освободившихся
слота, а журнал стартов подтверждает ровно один supervisor на каждую попытку.
Целевые тесты, polling-тест с внешним таймаутом, полный `go test -timeout 5m ./...`
и `just build` завершились PASS.

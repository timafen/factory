# CARD-0092 — Счётчик занятости воркера сам восстанавливается

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/b5b27bec-f6d-b21afa41-0ef`.
- Implementation commit: 7b0e963d2f8ae6c6d80570ed9af890b3b24501d7 — сервер выводит занятые слоты из живых lease и восстанавливает полную ёмкость после потери completion.
- What changed: registration и routing используют server-derived `active_count`, а не локальное число supervisors.
- What changed: reconnect-regression теперь считает реальные запуски barrier-supervisor для каждого attempt.
- Evidence: целевые проверки восстановления ёмкости и отсутствия двойного запуска PASS; полный набор выявил отдельный таймаут polling-теста.
- One next action: human merge after reviewing the unrelated polling-test timeout.

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

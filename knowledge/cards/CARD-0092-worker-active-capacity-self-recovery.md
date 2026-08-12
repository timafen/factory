# CARD-0092 — Счётчик занятости воркера сам восстанавливается

## HEAD

- Status: Implemented and verified.
- Branch: `factory/b5b27bec-f6d-b21afa41-0ef`.
- Implementation commit: 7b0e963d2f8ae6c6d80570ed9af890b3b24501d7 — сервер выводит занятые слоты из живых lease и восстанавливает полную ёмкость после потери completion.
- What changed: registration и routing используют server-derived `active_count`, а не локальное число supervisors.
- What changed: reconnect-regression теперь считает реальные запуски barrier-supervisor для каждого attempt.
- Evidence: `go test ./internal/controlplane ./internal/worker -run '^(TestClaimReconcilesStaleCachedCapacityWithoutWorkerRestart|TestReconnectAfterLostCompletionRestoresEveryWorkerSlot)$' -count=1` → PASS.
- One next action: перед merge выполнить полный набор проверок на этапе Verify.

## LOG

### 2026-08-11 — Implement

После потерянного ответа `/complete` и restart control plane worker снова заполняет
все два слота, но каждая новая barrier-попытка запускает supervisor ровно один раз.
Регрессия сохраняет отдельную запись каждого старта и отвергает повторный запуск для
того же attempt. Целевая интеграционная проверка worker завершилась PASS (8.652s).

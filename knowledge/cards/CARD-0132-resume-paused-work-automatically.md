# CARD-0132 — Снятая с паузы работа продолжает то же поколение

Implementation commit: 14f61511c1e2ccb997557c2a6efbc47ef928bd84 — успешный этап после денежной паузы создаёт ровно одного преемника в том же поколении.

## HEAD

- Status: Implemented — целевые проверки PASS; готово к Verify.
- Branch: `factory/79e00653-120-9e6c085e-092`.
- Implementation commit: 14f61511c1e2ccb997557c2a6efbc47ef928bd84 — пауза больше не поглощает успешный переход, а повторная попытка идемпотентна.
- What changed: terminal handoff during a pause remains unprocessed; after resume it preserves `work_id`, `parent_task_id`, and a deterministic request key.
- What changed: the ordinary cycle and the stall watcher reuse an already-created successor after a lost API response.
- Evidence: exact regression PASS; 28 Pilot area tests PASS; targeted control-plane test, `go build ./...`, 21 web tests, and web production build PASS.
- Known baseline: full Pilot suite ran 256 tests with 2 pre-existing restart-verdict failures also present on clean `HEAD`.
- One next action: провести Verify и затем влить ветку в `main`.

## LOG

### 2026-08-13 — Implement

Успешная terminal-задача во время денежной паузы раньше сразу попадала в `processed`, поэтому после снятия паузы не появлялся следующий этап. Теперь переход откладывается, а после возобновления создаётся один следующий этап с тем же `work_id` и родителем; обычный цикл и сторож используют общий детерминированный ключ и находят уже созданного преемника после потерянного ответа API. Точный регрессионный тест, 28 целевых тестов Pilot, control-plane тест и сборки прошли. Полный Pilot-набор сохраняет два исходных падения сценариев восстановления после перезапуска, воспроизводимых на чистом `HEAD`.

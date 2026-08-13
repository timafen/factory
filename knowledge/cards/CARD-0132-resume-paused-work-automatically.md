# CARD-0132 — Снятая с паузы работа продолжает то же поколение

Implementation commit: 14f61511c1e2ccb997557c2a6efbc47ef928bd84 — успешный этап после денежной паузы создаёт ровно одного преемника в том же поколении.

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/79e00653-120-9e6c085e-092`.
- Implementation commit: 14f61511c1e2ccb997557c2a6efbc47ef928bd84 — пауза больше не поглощает успешный переход, а повторная попытка идемпотентна.
- What changed: terminal handoff during a pause remains unprocessed; after resume it preserves `work_id`, `parent_task_id`, and a deterministic request key.
- What changed: the ordinary cycle and the stall watcher reuse an already-created successor after a lost API response.
- Evidence: 13 PipelineWatch tests PASS, включая снятие паузы и потерянный ответ API; `just check` прошёл Go-анализ и Go-тесты, а UI-проверка прошла 178 тестов. Два падения полного Pilot-набора воспроизведены на закреплённой базе.
- One next action: влить ветку в `main` после просмотра evidence Verify.

## LOG

### 2026-08-13 — Implement

Успешная terminal-задача во время денежной паузы раньше сразу попадала в `processed`, поэтому после снятия паузы не появлялся следующий этап. Теперь переход откладывается, а после возобновления создаётся один следующий этап с тем же `work_id` и родителем; обычный цикл и сторож используют общий детерминированный ключ и находят уже созданного преемника после потерянного ответа API. Точный регрессионный тест, 28 целевых тестов Pilot, control-plane тест и сборки прошли. Полный Pilot-набор сохраняет два исходных падения сценариев восстановления после перезапуска, воспроизводимых на чистом `HEAD`.

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Снятая пауза продолжает ту же работу | `PipelineWatchTests` в закреплённом кандидате | следующий Verify создан один раз с исходными `work_id`, `parent_task_id` и ключом handoff |
| Потерянный ответ create не создаёт дубль | `PipelineWatchTests` | сторож находит уже созданного преемника |
| Смежные пути не регрессируют | `just check`; UI после `npm ci` | Go vet/vuln/staticcheck и Go-тесты PASS; 178 UI-тестов PASS |

Полный Pilot-набор кандидата: 257 тестов, 2 падения `CorrectionProvenanceStormTests`; те же два падения и тот же стек воспроизводятся на закреплённой базе до поставки. `test-tooling` не завершился из-за внешней переменной `FACTORY_BUILD_DIR`, подменившей ожидаемый тестом `FACTORY_V2_BUILD_DIR`; это не касается изменённых файлов.

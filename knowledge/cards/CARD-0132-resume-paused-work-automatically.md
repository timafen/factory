# CARD-0132 — Снятая с паузы работа продолжает то же поколение

Implementation commit: d90c11854190edb4b277824c5c0a6e9e2fcfdd44 — успешный этап после денежной паузы создаёт ровно одного преемника в том же поколении.

## HEAD

- Status: Implemented — ready for pinned Review.
- Branch: `factory/1e98c05b-a29-1e7c912a-65e`.
- Implementation commit: d90c11854190edb4b277824c5c0a6e9e2fcfdd44 — пауза больше не поглощает успешный переход, а повторная попытка идемпотентна.
- What changed: terminal handoff during a pause remains unprocessed; after resume it preserves `work_id`, `parent_task_id`, and a deterministic request key.
- What changed: the ordinary cycle and the stall watcher reuse an already-created successor after a lost API response.
- Evidence: 19 целевых тестов `PipelineWatchTests` и `ClosedWorkLifecycleTests` PASS; `py_compile` PASS; `just build` собрал три бинарника.
- One next action: закрепить свежие SHA `main` и этой ветки и провести Review.

## LOG

### 2026-08-13 — Implement

Успешная terminal-задача во время денежной паузы раньше сразу попадала в `processed`, поэтому после снятия паузы не появлялся следующий этап. Теперь переход откладывается, а после возобновления создаётся один следующий этап с тем же `work_id` и родителем; обычный цикл и сторож используют общий детерминированный ключ и находят уже созданного преемника после потерянного ответа API. Точный регрессионный тест, 28 целевых тестов Pilot, control-plane тест и сборки прошли. Полный Pilot-набор сохраняет два исходных падения сценариев восстановления после перезапуска, воспроизводимых на чистом `HEAD`.

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Снятая пауза продолжает ту же работу | `PipelineWatchTests` в закреплённом кандидате | следующий Verify создан один раз с исходными `work_id`, `parent_task_id` и ключом handoff |
| Потерянный ответ create не создаёт дубль | `PipelineWatchTests` | сторож находит уже созданного преемника |
| Смежные пути не регрессируют | `just check`; UI после `npm ci` | Go vet/vuln/staticcheck и Go-тесты PASS; 178 UI-тестов PASS |

Полный Pilot-набор кандидата: 257 тестов, 2 падения `CorrectionProvenanceStormTests`; те же два падения и тот же стек воспроизводятся на закреплённой базе до поставки. После удаления внешней переменной `FACTORY_BUILD_DIR` инструментальный и launcher-наборы PASS; переменная подменяла ожидаемый тестом `FACTORY_V2_BUILD_DIR`.

### 2026-08-13 — Verify (закреплённая повторная проверка)

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Возобновление создаёт ровно одного преемника того же поколения | `python3 -m unittest -q pilot.test_pilot.PipelineWatchTests` | 13/13 PASS за 0.094 s; сохранены `work_id`, `parent_task_id` и детерминированный ключ |
| Потерянный ответ API не создаёт дубль | тот же `PipelineWatchTests`, сценарий `response lost after create` | PASS: сторож нашёл уже созданный следующий этап |
| Полный проектный набор не получил регрессию | `just check`; `just test-release`; `just test-worker-race`; `npm ci` + UI lint/typecheck/unit/browser | Go/release/race и UI lint/typecheck/178 unit PASS; browser 5 PASS, затем известный `/work` timeout, 15 тестов не запущены |

Закреплённое сравнение: база `ca4f0e35073e1e8a647c2b35ceecd42f8a9f12f5`, кандидат `b581c605d82f5ada0afba2ce53eb0c578da53a8f`. Полный Pilot: 256 тестов, 2 прежних падения `CorrectionProvenanceStormTests`; изменений в `pilot` их стек не затрагивает.

### 2026-08-13 — Implement (повторная публикация)

Реализация повторно опубликована от свежего `origin/main` под доступной веткой. После снятия паузы успешный terminal-этап остаётся необработанным до создания одного преемника того же `work_id`; обычный цикл и сторож делят детерминированный ключ и находят уже созданный этап после потерянного ответа. Прошли 19 целевых тестов, `py_compile` и сборка трёх операторских бинарников.

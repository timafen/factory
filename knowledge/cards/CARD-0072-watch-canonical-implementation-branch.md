# CARD-0072 — Сторож продолжает проверку с ветки настоящей реализации

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/1793a475-d50-d94bf866-fa6`.
- Implementation commit: 55fb2e163e4ad8686f97db1f863a62a860e72d31 — повторная обработка той же реализации сохраняет пересобранную delivery-ветку.
- What changed: `delivery_artifact` сбрасывается только при новой identity
  реализации или поколении; повтор terminal-задачи после restart сохраняет
  ветку, выбранную `review_gate`, до Review → Verify → merge.
- Evidence: targeted pipeline 6/6 OK; full `pilot.test_pilot` 183/183 OK;
  full `just check` OK; clean tree after verification.
- One next action: Human merge implementation commit after this Verify handoff.

## LOG

### 2026-08-11 — Specification

Подтверждены два разрыва в `pilot/pilot.py`: `pipeline_watch()` при создании
потерянной следующей стадии передаёт только имя работы, а созданную задачу не
добавляет в текущий снимок `tasks`. Поэтому переход после `AREA WAIT` теряет
ветку успешной реализации, а позднее обработанная отменённая стадия может не
увидеть уже живой Review и создать новый Implement.

Выбран минимальный контракт: в существующей долговечной записи работы хранить
только подтверждённый `branch` и полный `head` успешной `Implement + Test`.
Пустые, непубликовавшиеся и служебные candidates не меняют факт. Сквозной
pilot-regression должен проверить сохранение, Watch-handoff, same-cycle
deduplication и продолжение через Review/Verify/auto-answer/resume.

### 2026-08-11 — Implement

Коммит `16c213aba9ab0278ed3085c22967d3673992e94c` добавил поколенно-ограниченный
`implementation_artifact`, проверку опубликованной непустой ветки и единый
приоритет branch/head для Watch, handoff, вопросов, resume и auto-merge. Watch
нормализует созданную задачу в текущем снимке, поэтому поздний отменённый retry
видит уже живую следующую стадию. Доказательство: 11/11 целевых и 180/180 всех
тестов `pilot.test_pilot`, `py_compile` и `git diff --check` прошли.

### 2026-08-11 — Implement

Коммит `a1d91bcca6c11a9df71767ae9a05c7d689c1feb6` устранил замечание повторного
Review: чистая ветка, пересобранная `review_gate`, теперь записывается как
поколенно-ограниченный delivery artifact и остаётся выбранной для Review,
Verify, вопросов, resume и auto-merge; canonical branch/head сохранены как
fallback. Сквозной тест воспроизвёл rebuild → Review → Verify → merge, все 22
связанных теста, `py_compile` и `git diff --check` прошли.

### 2026-08-11 — Implement

Коммит `55fb2e163e4ad8686f97db1f863a62a860e72d31` устранил второй блокер Review:
повторная обработка уже успешной terminal-задачи Implement + Test теперь
сохраняет rebuilt `delivery_artifact`, если branch/head/task_id/generation не
изменились. Сквозной тест запускает restart/reprocess после `review_gate`
rebuild без подмены `record_implementation_artifact`, затем подтверждает
единую ветку в Review, Verify и merge; 6/6 тестов, `py_compile` и
`git diff --check` прошли.

### 2026-08-11 — Verify

| Acceptance criterion | Check | Result |
| --- | --- | --- |
| `review_gate` строит clean delivery branch и цепочка продолжает её использовать | `python3 -m unittest pilot.test_pilot.RebuiltDeliveryBranchPipelineTests` | PASS: rebuild → Review → Verify → `gh_merge` используют `factory/original-implementation-clean`; canonical implementation сохранён как fallback |
| Restart/reprocess той же успешной Implement-задачи не подменяет delivery artifact | тот же сквозной тест, `state["processed"] = []`, без mock `record_implementation_artifact` | PASS: новая Review не создаётся, delivery branch остаётся clean |
| Новая implementation generation сбрасывает старый delivery artifact | `python3 -m unittest pilot.test_pilot.CanonicalImplementationBranchTests` | PASS: новая task identity очищает старую delivery branch; canonical branch/head остаются доступными |
| Регрессии проекта отсутствуют | `just check` | PASS: Go tests, UI lint/typecheck/147 tests, tooling и launcher |
| Полный pilot regression отсутствует | `python3 -m unittest pilot.test_pilot` | PASS: 183 tests |

Проверка выполнена на implementation commit `55fb2e163e4ad8686f97db1f863a62a860e72d31`;
последующий commit меняет только эту карточку.

# CARD-0072 — Сторож продолжает проверку с ветки настоящей реализации

## HEAD

- Status: Implemented and targeted tests pass — awaiting Review.
- Branch: `factory/7341e44a-675-b7e7c7ff-d0a`.
- Implementation commit: a1d91bcca6c11a9df71767ae9a05c7d689c1feb6 — пересобранная delivery-ветка сохраняется до Verify и auto-merge.
- What changed: выбранная `review_gate` ветка хранится отдельно от canonical
  implementation artifact и проходит через Review → Verify → merge; новая
  реализация и новое поколение сбрасывают прежний выбор.
- Evidence: 22/22 связанных теста OK; `py_compile` и `git diff --check` — OK.
- One next action: Review подтверждает, что delivery-ветка не подменяется
  canonical fallback после перехода Review → Verify.

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

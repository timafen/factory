# CARD-0072 — Сторож продолжает проверку с ветки настоящей реализации

## HEAD

- Status: Implemented and tested — awaiting Review.
- Branch: `factory/607396d9-c82-f83b9850-8ef`.
- Implementation commit: 16c213aba9ab0278ed3085c22967d3673992e94c — сторож сохраняет подтверждённые branch/head настоящей реализации и продолжает с них.
- What changed: успешная `Implement + Test` закрепляет опубликованный непустой
  артефакт; Watch, Review, Verify, вопросы и resume предпочитают его случайной
  ветке поздней стадии. Созданная Watch задача сразу попадает в снимок цикла.
- Evidence: целевые классы — 11/11 OK; полный `pilot.test_pilot` — 180/180 OK;
  `py_compile` и `git diff --check` — OK.
- One next action: Review сверяет diff и сохранение canonical identity во всех
  переходах без повторного полного прогона.

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

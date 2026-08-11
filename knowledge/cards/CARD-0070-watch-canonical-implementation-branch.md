# CARD-0070 — Сторож продолжает проверку с ветки настоящей реализации

## HEAD

- Status: Specified — awaiting implementation.
- Specification: `knowledge/specs/watch-canonical-implementation-branch.md`.
- What changes: успешная `Implement + Test` станет сохранять подтверждённые
  branch/head; Watch, Review, Verify и resume продолжат с этого факта, а
  отменённый service retry не обойдёт уже созданный Review/Verify.
- Scope: только `pilot/pilot.py` и `pilot/test_pilot.py`; UI, worker,
  controlplane, `CARD-0069` и `CARD-0058` исключены.
- Implementation commit: будет добавлен этапом Implement после коммита кода;
  до него карточка намеренно не называет несуществующий SHA.

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

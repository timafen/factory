# CARD-0069 — Спецификация сохраняется в ветке до разработки

## HEAD

Implementation commit: 9bda146003105ee1bdbce2a1c290bc8e2cbf2b2b — Пилот проверяет сохранность спецификации перед разработкой.

- Status: Implemented and tested — awaiting Review.
- Branch: `factory/421ef5eb-ef6-3168645c-592`.
- Specification: `knowledge/specs/specification-branch-handoff.md`.
- What changed: переход запускает разработку только после подтверждения
  опубликованной ветки с непустым diff; временный сбой GitHub ждёт новый цикл.
- Evidence: `python3 -m unittest -v pilot.test_pilot.SpecificationBranchHandoffTests`
  → 8 tests, OK; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` → OK.
- Next action: проверить дифф и поведение ворот на стадии Review.

## LOG

### 2026-08-11 — Specification

Подтверждён разрыв в текущем переходе: опубликованная ветка выбирается и
проверяется только перед Review/Verify, тогда как Specification сразу создаёт
Implement + Test по имени ветки из текста. Выбран минимальный контракт: до
разработки ветка обязана существовать в origin и иметь непустой diff относительно
main; временная ошибка GitHub откладывает переход без ложного возврата.

### 2026-08-11 — Implement

Добавлены ворота сохранности перед `Implement + Test`: выбранная опубликованная
ветка обязана существовать и иметь непустой diff относительно `main`. Отсутствие
артефакта возвращает `Specification` с инструкцией commit/push, а временная ошибка
GitHub снимает задачу из `processed` для следующего цикла. Целевой набор: 8 tests,
OK; смежные ворота поставки: 9 tests, OK; `py_compile` и `git diff --check`: OK.

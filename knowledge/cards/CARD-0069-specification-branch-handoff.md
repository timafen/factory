# CARD-0069 — Спецификация сохраняется в ветке до разработки

## HEAD

- Status: Specification — awaiting implementation.
- Branch: `factory/c4ac71d1-d76-1c4781ba-6b7`.
- Implementation commit: pending — реализация ещё не начиналась на стадии Specification.
- Specification: `knowledge/specs/specification-branch-handoff.md`.
- What changes: Пилот не передаст работу из Specification в разработку, пока
  опубликованная ветка не содержит сохранённый артефакт спецификации.
- Evidence target:
  `python3 -m unittest -v pilot.test_pilot.SpecificationBranchHandoffTests`.
- Next action: реализовать ворота передачи в `pilot/pilot.py` и целевые сценарии
  в `pilot/test_pilot.py` по проверяемым обещаниям спецификации.

## LOG

### 2026-08-11 — Specification

Подтверждён разрыв в текущем переходе: опубликованная ветка выбирается и
проверяется только перед Review/Verify, тогда как Specification сразу создаёт
Implement + Test по имени ветки из текста. Выбран минимальный контракт: до
разработки ветка обязана существовать в origin и иметь непустой diff относительно
main; временная ошибка GitHub откладывает переход без ложного возврата.

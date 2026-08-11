# Передача ревизии Specification в Implement

## HEAD

Status: реализовано
Branch: factory/a47f517c-8df-d86ebd42-07d
Implementation commit: 8eb83e2b14225c40e76f4e9913afb4173ecb288a — уточнена обязательность отдельной карточки знаний
What changed: Pilot теперь явно требует отдельную карточку знаний при передаче Specification → Implement.
Evidence: `python3 -m unittest pilot.test_pilot.SpecificationBranchHandoffTests` → будет проверено после перебазирования.
One next action: перебазировать ветку на свежий `origin/main` и передать в Review.

## LOG

### 2026-08-11 — Implement

Добавлена стабильная строка `Specification head` при переходе Specification → Implement.
Целевой набор `SpecificationBranchHandoffTests` подтвердил точное совпадение полного SHA.

### 2026-08-11 — Implement

Карточка переименована в CARD-0082 из-за занятого номера.
Коммит реализации `8eb83e2b14225c40e76f4e9913afb4173ecb288a` сохранён в ветке;
изменён только `pilot/pilot.py`, карточка обновлена для текущей поставки.

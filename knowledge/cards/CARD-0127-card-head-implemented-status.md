# CARD-0127 — Статус `Implemented` в HEAD карточки

Implementation commit: db8e945503fe6b6491fa749d7a208fbaa990c12f — Review проверяет статус Implemented в HEAD опубликованной карточки

## HEAD

- Status: Implemented
- Branch: `factory/8544e80e-5aa-af4e85fd-524`
- Implementation commit: `db8e945503fe6b6491fa749d7a208fbaa990c12f` — Review проверяет статус Implemented в HEAD опубликованной карточки.
- What changed: Review читает `Status: Implemented` только из секции HEAD карточки и возвращает старый, отсутствующий или чужой статус в Implement. Ошибка чтения remote остаётся повторяемой инфраструктурной проверкой.
- Evidence: `python3 -m unittest -v pilot.test_pilot.CardHeadStatusTests` и три существующих card-gate теста → 8 PASS; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` и `git diff --check` → PASS.
- One next action: Review проверяет опубликованную ветку и свежую базу перед созданием Review.

## LOG

### 2026-08-14 — Implement

Добавлена машинная проверка `Status: Implemented` в секции HEAD опубликованной карточки перед Review; независимая проверка implementation commit сохранена. Целевые тесты покрывают допустимый статус, старый/отсутствующий и вынесенный из HEAD статус, чужую карточку и ошибку remote.

Проверено: `python3 -m unittest -v pilot.test_pilot.CardHeadStatusTests` и три существующих card-gate теста → 8 PASS; `py_compile` и `git diff --check` → PASS.

### 2026-08-13 — Specification

Карточка создана для проверки, что Review принимает только явно зафиксированный `Status: Implemented` в опубликованном HEAD. Область: `pilot/pilot.py`, `pilot/test_pilot.py` и связанная спецификация. План: добавить ворота статуса, не ослабляя проверки SHA, номера карточки, scope и свежей базы; при сетевой ошибке remote использовать повторяемый infrastructure block.

# CARD-0079 — Спецификация публикует карточку своей работы

## HEAD

Status: реализовано, проверки зелёные
Branch: `factory/0b8e75e4-75c-eb8b5da4-4b8`
Implementation commit: 3923b6e8dc365c5c4847c4a2c3886c9ed068bdc0 — migration025 закрепляет правила публикации карточки текущей работы

What changed: Specification берёт карточку из `Card:`/пути в context, а без неё
создаёт отдельную карточку текущей работы; фиксированная CARD-0074 запрещена.
Revision 8 меняет только документы этапа и требует commit/push.

Evidence: `go test ./...` → OK; целевые migration-тесты → OK;
`python3 -m unittest -v pilot.test_pilot.SpecificationBranchHandoffTests` → 15 OK;
`go build ./...` и `git diff --check` → OK.

One next action: влить ветку в `main` после проверки.

## LOG

### До 2026-08-11 — Specification

Implementation commit: 2edcd9b1890c3419952297b4eadc4b5d300f46dd — исправлены правила публикации документов этапа Specification

## Суть

Specification должна публиковать спецификацию и отдельную карточку именно
текущей работы. Фиксированная ссылка на CARD-0074 недопустима: она связывает
параллельную задачу с чужим документом.

## Объём

- обновить immutable revision prompt для Specification;
- выбирать карточку из контекста, а при его отсутствии — свободный номер;
- добавить upgrade- и handoff-проверки, гарантирующие отсутствие CARD-0074 как
  универсального значения;
- не менять продуктовый код, UI, CARD-0074 и общие журналы.

## Проверка

Ожидается целевая проверка `python3 -m unittest -v
pilot.test_pilot.SpecificationBranchHandoffTests` с кейсом, где две работы
получают разные карточки и handoff передаёт карточку своей работы.

## Статус

Карточка подготовлена для этапа Specification; реализация перечислена в
спецификации и должна быть выполнена последующим этапом.

### 2026-08-11 — Implement

Добавлена immutable migration025 поверх живой revision 7: новая revision 8
использует карточку из context либо отдельную карточку текущей работы и не
подменяет её CARD-0074. Целевые Go-тесты, полный `go test ./...`, 15 Python
handoff-тестов, `go build ./...` и `git diff --check` завершились успешно.

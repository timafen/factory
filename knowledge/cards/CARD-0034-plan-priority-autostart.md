# CARD-0034 — Автоподбор верхней карточки Плана

## HEAD

- Status: Specification recorded; pilot changes excluded from this delivery
- Branch: `factory/ebe3ad49-658-9767151e-763`
- Head commit: `4d53078` — «Убрать чужие правки пилота из поставки»
- What changed: в поставке остались только карточка и спецификация автоподбора;
  изменения `pilot/pilot.py` и `pilot/test_pilot.py` возвращены к `origin/main`.
- Evidence: `python3 -m unittest pilot.test_pilot` — PASS, 1 тест;
  `go build ./...` — PASS.
- Next action: выполнить автоподбор отдельной поставкой с согласованной областью `pilot/`.

## LOG

### 2026-08-08 — Specification

Зафиксированы слот менее трёх уникальных работ, учёт ожидания владельца,
денежные пределы, Triage-контекст и тихий журнал `routine`.

### 2026-08-08 — Implement

Добавлен автозапуск одной верхней карточки с Triage-контекстом и переводом в
`in_work` только после создания задачи. Целевые 4 Python-теста и сборка обоих
Go-бинарников прошли. Общий Go-набор сохраняет независимый существующий сбой
`TestHTTPManagedRepositoryCatalog` (404 вместо 200).

### 2026-08-08 — Delivery scope correction

Машинная проверка исключила `pilot/pilot.py` и `pilot/test_pilot.py` как чужие
файлы. Они возвращены к `origin/main`; проверка спецификации и сборка проходят,
но реализация автоподбора должна прийти отдельной согласованной поставкой.

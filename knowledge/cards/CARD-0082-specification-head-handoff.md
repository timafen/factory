# Передача ревизии Specification в Implement

## HEAD

Status: Verified PASS — deployed from main
Branch: factory/8d74f2e0-c74-770a846b-fd7
Implementation commit: bee395269e7fc5e6aeba0c3a44077442f48ea968 — второй независимый невалидный Specification HEAD не создаёт Implement.
What changed: Factory выложена из `main` с точной передачей Specification HEAD и жёсткой остановкой после исчерпания rescue.
Evidence: `fx factory release-info --technical` → `07491cc7b26bbc47dca9f8fd5109f2c665f1fa53`; Pilot → 196 tests, UI → 158 tests, typecheck/build → OK; `go build ./...` → OK.
One next action: merge the card evidence update into main.

## LOG

### 2026-08-11 — Implement

После подтверждения, что `bee395269e7fc5e6aeba0c3a44077442f48ea968` входит в
свежий `origin/main`, Factory выложена из `07491cc7b26bbc47dca9f8fd5109f2c665f1fa53`.
Повторный Verify подтвердил 196 Pilot-тестов, 158 UI-тестов,
UI typecheck/build и Go build; для перегруженного хоста UI timeout увеличен до 30 секунд.

### 2026-08-11 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Строгий полный SHA | `SpecificationBranchHandoffTests` | missing/short/malformed HEAD отклонены, полный SHA принят |
| Исчерпанный rescue | Два независимых Specification в циклах | только один rescue, Implement не создан |
| Guard обязателен | Мутация production guard | целевой тест падает с `2 != 1` |
| Реальный SHA реализации | `git merge-base --is-ancestor` и `git diff-tree` | `bee3952…` — предок ветки и меняет `pilot/pilot.py` |
| Upgrade текущего main | `go test ./internal/controlplane` на `origin/main` | успешно |

### 2026-08-11 — Implement

Исправлен blocker проверки: повторный цикл больше не возвращает ту же задачу из
`processed`. Две отдельные успешные Specification с разными task/execution/attempt ID
подтверждают один rescue, ясную жёсткую остановку и отсутствие Implement; implementation
commit — `bee395269e7fc5e6aeba0c3a44077442f48ea968`.

### 2026-08-11 — Implement

Исправлен обход HEAD-gate после исчерпания cap_rescues: второй невалидный результат
останавливается до Implement. Тест двух циклов подтверждает отсутствие задачи Implement;
реальный implementation commit — `86f9d14f6247e3006980d0761bb7d1f068df4d64`.

### 2026-08-11 — Implement

Добавлена стабильная строка `Specification head` при переходе Specification → Implement.
Целевой набор `SpecificationBranchHandoffTests` подтвердил точное совпадение полного SHA.

### 2026-08-11 — Implement

Карточка переименована в CARD-0082 из-за занятого номера.
Коммит реализации `8eb83e2b14225c40e76f4e9913afb4173ecb288a` сохранён в ветке;
изменён только `pilot/pilot.py`, карточка обновлена для текущей поставки.

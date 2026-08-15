# CARD-0070 — Уникальные номера карточек параллельных работ

## HEAD

Status: Verified PASS — awaiting human merge
Branch: factory/5b9cb945-2d5-c61f3f8a-cb6
Implementation commit: bee395269e7fc5e6aeba0c3a44077442f48ea968 — после исчерпания возврата второй невалидный HEAD не запускает Implement.
Specification: после конфликта в `main` сохранён контракт уникального резерва номера и точная целевая регрессия для следующего сопровождения.
Evidence summary: `just check`, сборка, UI unit/browser и целевые 23 Python-теста прошли; мутация без production guard падает.
One next action: human merge into main.

- Status: Implemented and tested — уникальные номера и строгий HEAD-gate исправлены.
- Branch: `factory/5b9cb945-2d5-c61f3f8a-cb6`.
- What changed: после первого SPEC_HEAD rescue повторный missing/short/malformed HEAD безопасно останавливает переход в Implement; добавлен cycle test.
- Evidence: `python3 -m unittest pilot.test_pilot.SpecificationBranchHandoffTests` → 18 tests, `OK`.
- Next action: Провести независимый Review и слить ветку в `main`.

### 2026-08-11 — Implement

Обновлена доказательная регрессия для двух независимых Specification после конфликта
нумерации карточек; implementation commit — `bee395269e7fc5e6aeba0c3a44077442f48ea968`.

### 2026-08-11 — Implement

После конфликта сохранены CARD-0070/CARD-0082 и добавлен жёсткий ворот Specification → Implement:
отсутствующий, короткий или malformed `HEAD` возвращает Specification, точный полный SHA принимается.
Целевые `SpecificationBranchHandoffTests` и полный Python-набор прошли; `py_compile` и `git diff --check` чисты.

## LOG

### 2026-08-15 — Specification

Уточнён воспроизводимый контракт поставки после конфликта: номер карточки
резервируется по опубликованной ветке до создания Implement, сохраняется во
всех handoff и сверяется перед Review. Реальными точками сопровождения остаются
`pilot/pilot.py` и `pilot/test_pilot.py`; обязательная целевая проверка —
`CardNumberReservationTests` вместе с `SpecificationBranchHandoffTests`.

### 2026-08-11 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Параллельные ветки резервируют разные номера | `CardNumberReservationTests` | `CARD-0070`, `CARD-0071`; повтор сохраняет `CARD-0070` |
| Второй невалидный Specification не создаёт Implement | `SpecificationBranchHandoffTests` | 23 теста, `OK`; один rescue, затем `SPEC HEAD STOP` |
| Guard обязателен | Мутация без stop-ветки | целевой тест падает: `2 != 1` |
| Сборка и UI | `just build`, `just ui-check`, `just test-browser` | успешно |
| Upgrade текущего main | `go test ./internal/controlplane` на `origin/main` | успешно |

### 2026-08-11 — Implement

После исчерпания cap_rescues для SPEC_HEAD второй невалидный результат больше не обходится
условием gate: конвейер останавливается до создания Implement. Регрессионный cycle test
подтвердил один rescue и отсутствие Implement task; implementation commit — `86f9d14f6247e3006980d0761bb7d1f068df4d64`.

### 2026-08-11 — Implement

Добавлен устойчивый реестр резервов в состоянии Пилота. Две параллельные
опубликованные ветки получают последовательные разные номера, а повтор одной
ветки использует прежний номер. Недоступный каталог карточек откладывает
переход без угадывания номера. В контексте и правилах исполнителя закреплена
строка `Card:`, а ворота перед Review отклоняют карточку с другим номером.

Целевые 13 тестов и `python3 -m py_compile pilot/pilot.py` прошли успешно;
`git diff --check` не нашёл ошибок пробелов.

### 2026-08-11 — Implement

После конфликта автоматического слияния возврат из Verify теперь переносит
`Card:` в контекст повторного Implement. Регрессионный сценарий проводит
закреплённый номер через этот возврат и подтверждает его передачу в Review.
Целевые 15 тестов, `py_compile` и `git diff --check` прошли успешно.

### 2026-08-11 — Implement

Контекст стал источником истины для номера карточки: поздний отчёт Verify с
другим `Card:` больше не подменяет закреплённый резерв. Регрессия моделирует
конфликт слияния, повторный Implement и передачу в Review, не допуская
`CARD-0071` вместо `CARD-0070`. Целевые 6 тестов, `py_compile` и
`git diff --check` прошли успешно.

### 2026-08-11 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Параллельные работы получают разные номера | `python3 -m unittest pilot.test_pilot.CardNumberReservationTests.test_parallel_branches_reserve_distinct_numbers_and_retry_keeps_one` | `CARD-0070`, `CARD-0071`, повтор → `CARD-0070`; `OK` |
| Поздний отчёт не заменяет закреплённый номер | `python3 -m unittest pilot.test_pilot.CardNumberReservationTests.test_handoff_keeps_card_from_context_or_stage_report pilot.test_pilot.PipelineWatchMergeTests.test_merge_conflict_keeps_context_card_despite_verify_report_to_review` | конфликт/повторный Implement передали в Review `CARD-0070`, не `CARD-0071`; `OK` |
| Полный проектный набор и регрессии | `just test` → `go test -timeout 5m ./...` | все пакеты `ok` или `no test files`, exit `0` |
| Карточка и implementation SHA | `git show`, `git merge-base --is-ancestor`, сравнение номеров с `origin/main` | SHA существует, предок ветки, меняет `pilot/`; `CARD-0070` новый |

### 2026-08-11 — Implement

Ветка задачи перенесена на актуальное состояние рабочего окружения и проверена
после продвижения `main`; в конфликте `pilot/pilot.py` сохранены одновременно
`Card:` во всех handoff и `Implementation head` с канонической delivery-веткой.
Целевые 7 unittest, `py_compile`, `git diff --check` и полный `just test` прошли.

### 2026-08-11 — Implement

После перебазирования на актуальный `main` исправлен merge-conflict rescue:
повторный Implement получает вместе каноническую delivery-ветку, полный
`Implementation head` и закреплённый `Card:`. Регрессионный сценарий также
проверяет передачу `expected_card` в review gate. Кодовый коммит:
`662de7f877f1de43ea5f240d348c688d2447b6d5`. Целевые 28 unittest,
`py_compile`, `git diff --check` и полный `just test` прошли успешно.

# CARD-0070 — Уникальные номера карточек параллельных работ

## HEAD

Implementation commit: c34efaa6d0c69a9d8c39fca60125806edfb85a45 — Пилот резервирует уникальный номер карточки и переносит его через handoff.

- Status: Verified PASS — ветка обновлена после продвижения `main`.
- Branch: `factory/35156296-93f-8e395a67-293`.
- What changed: закреплённая строка `Card:` сохраняется в handoff, а `Implementation head`
  и каноническая delivery-ветка не теряются при конфликтном возврате из Verify.
- Evidence: 7 целевых unittest → `OK`; `python3 -m py_compile pilot/pilot.py` → exit 0;
  `git diff --check` → exit 0; `just test` → exit 0.
- Next action: Проверить PR и слить ветку.

## LOG

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

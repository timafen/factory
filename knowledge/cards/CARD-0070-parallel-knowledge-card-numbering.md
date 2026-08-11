# CARD-0070 — Уникальные номера карточек параллельных работ

## HEAD

Implementation commit: 662de7f877f1de43ea5f240d348c688d2447b6d5 — Пилот сохраняет идентичность реализации при возврате после конфликта слияния.

- Status: Implemented and tested — блокеры независимого Review исправлены.
- Branch: `factory/4f3be794-214-3c24b813-cfc`.
- What changed: rescue-handoff после merge conflict одновременно сохраняет `Card:`,
  `Implementation head` и каноническую delivery-ветку; тест проверяет все три поля.
- Evidence: 28 целевых unittest → `OK`; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` → exit 0;
  `git diff --check` → exit 0; `just test` → exit 0.
- Next action: Провести независимый Review и слить ветку в `main`.

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

### 2026-08-11 — Implement

После перебазирования на актуальный `main` исправлен merge-conflict rescue:
повторный Implement получает вместе каноническую delivery-ветку, полный
`Implementation head` и закреплённый `Card:`. Регрессионный сценарий также
проверяет передачу `expected_card` в review gate. Кодовый коммит:
`662de7f877f1de43ea5f240d348c688d2447b6d5`. Целевые 28 unittest,
`py_compile`, `git diff --check` и полный `just test` прошли успешно.

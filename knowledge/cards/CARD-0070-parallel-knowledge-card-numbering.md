# CARD-0070 — Уникальные номера карточек параллельных работ

## HEAD

Implementation commit: 0c1232d7d9f4e05ab96b07a91c76f0d93077fadf — Пилот сохраняет закреплённый номер из контекста, даже если Verify сообщил другой.

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/bd28a54c-43a-974ba111-3c4`.
- What changed: закреплённая строка `Card:` из контекста имеет приоритет над поздним отчётом этапа.
  Verify с другим номером не меняет карточку повторного Implement или последующего Review.
- Evidence: три целевых unittest-сценария, включая параллельное резервирование и
  merge-conflict handoff → OK; `just test` (`go test -timeout 5m ./...`) → exit 0;
  `CARD-0070` отсутствует в `origin/main` и единственна среди новых номеров ветки.
- Next action: Человеку слить ветку после просмотра evidence.

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

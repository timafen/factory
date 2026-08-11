# CARD-0070 — Уникальные номера карточек параллельных работ

## HEAD

Implementation commit: 5849057e79d935d49e30b603d3921289ddfe3170 — Пилот резервирует уникальный номер карточки для опубликованной ветки.

- Status: Implemented — awaiting Review.
- Branch: `factory/e7b754fc-fcb-63573b74-3e5`.
- What changed: до запуска разработки номер сохраняется за парой репозиторий/ветка;
  он передаётся в Implement, Review и Verify и проверяется перед Review.
- Evidence: `python3 -m unittest -v pilot.test_pilot.CardNumberReservationTests pilot.test_pilot.SpecificationBranchHandoffTests` → 13 tests, OK.
- Next action: Review проверить изменение и целевые регрессии.

## LOG

### 2026-08-11 — Implement

Добавлен устойчивый реестр резервов в состоянии Пилота. Две параллельные
опубликованные ветки получают последовательные разные номера, а повтор одной
ветки использует прежний номер. Недоступный каталог карточек откладывает
переход без угадывания номера. В контексте и правилах исполнителя закреплена
строка `Card:`, а ворота перед Review отклоняют карточку с другим номером.

Целевые 13 тестов и `python3 -m py_compile pilot/pilot.py` прошли успешно;
`git diff --check` не нашёл ошибок пробелов.

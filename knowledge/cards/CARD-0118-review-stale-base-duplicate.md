# CARD-0118: закрыть повторное усиление Review от устаревшей базы

Implementation commit: fc056fc4f3c7785b00be164b190572b9101fe030 — Review принимает область только из двух полных SHA.

## HEAD

Status: Done — отдельная поставка восстановления защиты Review.
Branch: `factory/68adf6b1-140-2269df62-22c`
Implementation commit: fc056fc4f3c7785b00be164b190572b9101fe030 — Review строит diff только как `base_sha...candidate_sha`, оба значения валидируются как полные SHA.
What changed: добавлен единый валидатор pinned-диапазона и целевой тест на отказ от имён ссылок и сокращённых идентификаторов.
Evidence: `python3 -m unittest -q pilot.test_pilot.FreshDefaultBranchSnapshotTests` → 7 tests, OK; `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` → OK.
One next action: выполнить независимые Review и Verify для опубликованной ветки.

## LOG

### 2026-08-13 — Implement

На свежем удалённом снимке подтверждено, что защита Review уже поставлена в
`main`: реализация меняет `pilot/pilot.py` и `pilot/test_pilot.py`. Повторное
изменение продуктового кода не делалось; шесть целевых проверок завершились
успешно и подтверждают свежую pinned-базу, точный scope и fail-closed поведение.

### 2026-08-13 — Implement

Восстановлена отдельная поставка `pilot/pilot.py` и `pilot/test_pilot.py`:
область Review теперь формируется через проверенный полный диапазон
`base_sha...candidate_sha`, а тест фиксирует отказ от устаревающих ссылок.
Целевые 7 проверок, компиляция Python и проверка пробелов прошли успешно.

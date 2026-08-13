# CARD-0118: закрыть повторное усиление Review от устаревшей базы

Implementation commit: fc056fc4f3c7785b00be164b190572b9101fe030 — Review принимает область только из двух полных SHA.

## HEAD

Status: Verified PASS — awaiting human merge.
Branch: `factory/68adf6b1-140-2269df62-22c`
Implementation commit: fc056fc4f3c7785b00be164b190572b9101fe030 — Review строит diff только как `base_sha...candidate_sha`, оба значения валидируются как полные SHA.
What changed: добавлен единый валидатор pinned-диапазона и целевой тест на отказ от имён ссылок и сокращённых идентификаторов.
Evidence: pinned comparison `cd5c93b488fe6f7694f59d1e6b8d5e5abd58af91...e841fc222b3c64d9de168279a74fb27d63b802f3`; 7 целевых тестов и компиляция OK; web 173 теста, typecheck, lint и build OK. Полный Python-набор: 254 теста, 2 pre-existing failures в `CorrectionProvenanceStormTests`, вне изменённых функций.
One next action: human merge the verified implementation branch.

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

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Review использует свежую удалённую базу и полный pinned-диапазон | `python3 -m unittest -v pilot.test_pilot.FreshDefaultBranchSnapshotTests` | 7/7 OK: authoritative default ref, stale cache, remote advance и точный `base_sha...candidate_sha` |
| Ошибка получения refs блокирует Review, а пустая поставка не проходит | тот же целевой набор | OK: `BLOCKED: review infrastructure`; empty delivery возвращается с одной причиной |
| Соседний Verify обновляет snapshot перед merge | тот же целевой набор | OK: `verify_gate` вызывает свежий snapshot и блокирует инфраструктурную ошибку |
| Поставка не ломает проект | `python3 -m unittest -v pilot.test_pilot`; `(cd web && npm test -- --run)`; typecheck/lint/build | web 173/173 OK; Python 254, 2 failures в несвязанном `CorrectionProvenanceStormTests`; typecheck/lint/build OK |

Закреплённые SHA: base `cd5c93b488fe6f7694f59d1e6b8d5e5abd58af91`, candidate `e841fc222b3c64d9de168279a74fb27d63b802f3`.

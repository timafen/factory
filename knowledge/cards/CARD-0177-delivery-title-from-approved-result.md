# CARD-0177 — Название поставки из подтверждённого результата

Implementation commit: ed6db3022d41df2f6831ce39e8f9b15e26587825 — слияние, выпуск и уведомления получают проверенное человеческое название результата.

## HEAD

- Status: Implemented
- Branch: factory/38a2bd47-818-69b5c618-3bc
- Что изменилось: Pilot сохраняет подтверждённый implementation SHA, выбирает subject коммита либо один валидный `DELIVERY_TITLE` и проводит название через весь delivery state.
- Evidence: `python3 -m unittest -v pilot.test_pilot.DeliveryTitleTests` → 7 tests, OK; `python3 -m unittest pilot.test_pilot` → 350 tests, OK (13 skipped); `python3 -m py_compile pilot/pilot.py pilot/test_pilot.py` → exit 0.
- Следующее действие: провести Review реализации и соответствия публичных названий утверждённому результату.

## LOG

### 2026-08-15 — Implement

Добавлен строгий выбор названия поставки из подтверждённого коммита или явного override без fallback на исходную проблему. Название сохраняется при рестарте и merge conflict, попадает в PR, receipt, release wait и успешные/аварийные уведомления. Целевые 7 тестов и полный набор из 350 тестов прошли успешно; синтаксис обоих Python-файлов проверен.

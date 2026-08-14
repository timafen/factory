# CARD-auto-pilot-tests-release-gate

Implementation commit: c648f4a4 — исправлены сценарии AdaptivePollingTests и включён обязательный Pilot release-gate.

## Результат

Повторная задача закрыта как дубликат. Реализация уже влита в `main` через PR #220: `AdaptivePollingTests` проходят 24/24, а `python3 -m unittest pilot.test_pilot` выполняется в обязательной параллельной группе release до сборки. Полигон `FACTORY_RELEASE_TEST_TIMEOUT=60 bash ops/test-fx-factory-release.sh` прошёл по отчёту владельца.

## Объём реализации

- `pilot/pilot.py` — логика восстановления и идемпотентного продолжения после перезапуска.
- `pilot/test_pilot.py` — регрессионные проверки `AdaptivePollingTests`.
- `ops/fx-factory-release` — обязательный параллельный Pilot gate.
- `ops/test-fx-factory-release.sh` — проверка gate и его порядка.

## Решение владельца

Новых действий нет: ветку дубликата не мёржить, новый выкат не запускать. Карточка служит переносом результата в текущую спецификацию.

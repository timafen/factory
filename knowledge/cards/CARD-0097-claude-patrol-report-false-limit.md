Implementation commit: 8cc2241c10a77fe49fe856ae88144d293fc4b5e6 — определён безопасный контракт реализации: слова в отчёте патруля не могут блокировать всю подписку Claude.

# CARD-0097 — Отчёт патруля не блокирует подписку Claude

- Status: specification — передано в реализацию.
- Branch: `factory/eec22795-7e6-fab5221c-60b`.
- Specification: `knowledge/specs/claude-patrol-report-does-not-block-subscription.md`.
- Owner result: успешный или отменённый патруль может обсуждать лимиты в отчёте,
  не отключая Claude-исполнителей и не отправляя всю работу на запасной
  провайдер.
- Scope: `pilot/pilot.py`, `pilot/test_pilot.py`; UI, worker, control-plane,
  API, миграции и сохранённая схема состояния не меняются.
- Required check:
  `python3 -m unittest pilot.test_pilot.ProviderLimitDetectionTests`.

## Передача в реализацию

1. Сначала добавить регрессию успешного Claude-патруля с фразой
   `rate limit reached` в `attempt.result` и отсутствующим свежим снимком
   подписки: `note_limit()` не вызывается.
2. В `detect_limits()` доверять только `attempt.error` последней failed attempt
   у task со state `failed`; никогда не классифицировать `attempt.result` как
   состояние подписки.
3. Сохранить `INFRA_SIGNS`, извлечение `RESET_AT`, ручной блок и отдельную
   блокировку по реальному 95%-счётчику в `provider_limits_tick()`.
4. Проверить парные положительные и отрицательные сценарии точечным классом,
   затем выполнить полный `python3 -m unittest pilot.test_pilot`.

## Доказательство спецификации

Фактический путь ложной блокировки прослежен от терминальных задач через
объединение `attempt.error + attempt.result` в `detect_limits()` до
provider-wide `note_limit()`. Критерии приёмки разделяют свободный отчёт и
доверенную runtime-ошибку, а обязательный тест воспроизводит именно исходный
патрульный сценарий.

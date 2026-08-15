Implementation commit: f0d724e600d5c6557237a76348c278b2e44a9b3c — блок Claude теперь опирается только на ошибку последней failed-попытки

# CARD-0173: Отчёт патруля не блокирует подписку Claude

## HEAD

Status: Implemented
Branch: factory/3b9658b2-857-3086c298-fec
Specification: `knowledge/specs/claude-subscription-report-false-block.md`
What changed: `detect_limits()` игнорирует результаты succeeded/cancelled задач
и свободный `result`; лимит распознаётся по `error` последней failed-попытки.
Evidence: `python3 -m unittest pilot.test_pilot.ProviderLimitDetectionTest` —
6 тестов прошли; `python3 -m py_compile pilot/pilot.py` — успешно.
One next action: Verify выполняет один полный проектный прогон перед слиянием.

## LOG

### 2026-08-15 — Specification

Установлена остаточная причина после прежней частичной защиты: `detect_limits()`
анализирует даже успешные задачи и ищет признаки лимита в объединении `error` с
`result` двух последних попыток. Поэтому текст отчёта может вызвать глобальный
`note_limit()` при отсутствующем или устаревшем снимке процентов.

Определена граница исправления: только `error` последней failed-попытки является
доказательством текстового лимита. Результаты успешных, failed и cancelled
задач не классифицируются по содержимому отчёта. Настоящая терминальная ошибка
Claude сохраняется worker отдельно в `error`, поэтому положительный сценарий
остаётся проверяемым без эвристики по свободному тексту.

Номер `CARD-0173` выбран после проверки свежего `origin/main` и всех 1257
опубликованных remote refs: номера до `CARD-0172` заняты, путь этой карточки не
использовался.

### 2026-08-15 — Implement

Автоматическая классификация лимита сужена до непустого `error` последней
failed-попытки. Свободные отчёты успешных, failed и cancelled задач больше не
могут вызвать `note_limit()`, а настоящий limit error сохраняет извлечение
`resets_at` и инфраструктурное исключение.

Доказательство: обязательный `ProviderLimitDetectionTest` прошёл 6 сценариев;
`python3 -m py_compile pilot/pilot.py` и `git diff --check` завершились успешно.

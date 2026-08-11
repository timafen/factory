# Безопасное обновление всех worker-служб

Implementation commit: c2f7ad8b64d5a68da054c0b5e60ea8fbbc78ac0e — выпуск управляет списком worker-служб

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: factory/7907240b-8c8-5e39d767-6f2
- Implementation commit: c2f7ad8b64d5a68da054c0b5e60ea8fbbc78ac0e — выпуск управляет списком worker-служб
- What changed: `FACTORY_WORKER_SERVICES` задаёт все службы; остановка, запуск и откат выполняются для каждой.
- Evidence: `bash ops/test-fx-factory-release.sh` → PASS: остановка и запуск двух служб, а также откат с перезапуском обеих; `bash -n ops/fx-factory-release` → PASS. Полный `just check` дошёл до всех Go-пакетов, но завершился внешним таймаутом `TestClaudeCodeWorkerUsesTheSameConcurrentPool` в `internal/worker`.
- One next action: принять решение о слиянии с учётом отдельного таймаута теста пула Claude worker.

## LOG

### 2026-08-11 — Implement

Добавлен безопасный общий цикл управления несколькими worker-службами с обратной совместимостью для одной службы. Целевой тест подтвердил обновление и откат пары worker-служб.

### 2026-08-11 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Все заданные worker-службы останавливаются перед проверкой регистрации и запускаются после неё | `bash ops/test-fx-factory-release.sh` | PASS: зафиксированы `stop` и `start` для `factory-worker.service` и `factory-worker-2.service` в нужном порядке. |
| Откат возвращает работу каждой worker-службы | тот же изолированный сценарий, включая ошибки сервера, worker, установки и сигналы | PASS: после каждого отката зафиксирован перезапуск сервера и обеих worker-служб. |
| Без переменной сохраняется одна штатная служба | просмотр и синтаксическая проверка `ops/fx-factory-release` | PASS: значение `FACTORY_WORKER_SERVICES` по умолчанию равно `FACTORY_WORKER_SERVICE`, чьё штатное значение — `factory-worker.service`. |
| Изменение не ломает общие проверки | `just check` из чистого дерева | BLOCKED вне области: после прохождения остальных Go-пакетов истёк таймаут `TestClaudeCodeWorkerUsesTheSameConcurrentPool` в `internal/worker`; выпускной сценарий прошёл отдельно. |

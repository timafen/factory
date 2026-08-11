# Безопасное обновление всех worker-служб

Implementation commit: c2f7ad8b64d5a68da054c0b5e60ea8fbbc78ac0e — выпуск управляет списком worker-служб

## HEAD

- Status: реализовано
- Branch: factory/7907240b-8c8-5e39d767-6f2
- Implementation commit: c2f7ad8b64d5a68da054c0b5e60ea8fbbc78ac0e — выпуск управляет списком worker-служб
- What changed: `FACTORY_WORKER_SERVICES` задаёт все службы; остановка, запуск и откат выполняются для каждой.
- Evidence: `bash ops/test-fx-factory-release.sh` → PASS; `bash -n ops/fx-factory-release` → PASS.
- One next action: повторно проверить ветку на Review после push.

## LOG

### 2026-08-11 — Implement

Добавлен безопасный общий цикл управления несколькими worker-службами с обратной совместимостью для одной службы. Целевой тест подтвердил обновление и откат пары worker-служб.

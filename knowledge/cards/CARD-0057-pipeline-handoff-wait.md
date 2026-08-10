Implementation commit: aacb4cc48ff34d599973190524ca712212a1964f — ожидание перед восстановлением перехода сокращено с 600 до 450 секунд

# CARD-0057 — Ускорение переходов конвейера

## HEAD

- Status: Implemented — awaiting Verify.
- Branch: `factory/77352d66-dec-a0518147-b88`.
- What changed: патруль восстанавливает потерянный переход через 450 секунд, на 25% быстрее прежнего; сохранённые Automation-инструкции обновляются без противоречивого старого срока.
- Evidence: `python3 -m unittest pilot.test_pilot.PipelineWatchTests` → 7 tests OK; `go test ./internal/controlplane -run '^TestPipelinePatrol' -count=1` → PASS.
- One next action: повторить этап Verify на доставленной ветке.

## LOG

### 2026-08-10 — Implement

Окно безопасного ожидания сокращено с 600 до 450 секунд в Pilot и Automation-патруле. Тесты подтверждают отсутствие раннего запуска на 449-й секунде, продолжение с 450-й секунды и замену старой инструкции без потери пользовательского контекста. Целевые 7 Python-тестов и Go-тесты патруля прошли; `git diff --check` чист.

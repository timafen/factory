# CARD-0098 — Конкурентные Claude health-probe ждут занятый probe

Implementation commit: b083860744997c99646b43a831a991e6df515d02 — health-check ограниченно ждёт совпадающую команду, не ослабляя общий неблокирующий запуск.

## HEAD

- Status: Implemented and targeted tests PASS — awaiting Verify.
- Branch: `factory/9eee6045-e93-89a5e39d-2d3`.
- Implementation commit: b083860744997c99646b43a831a991e6df515d02 — health-check ограниченно ждёт совпадающую команду, не ослабляя общий неблокирующий запуск.
- Specification: `knowledge/specs/concurrent-claude-health-probes.md`.
- What changed: все короткие command-probe в `checkHealth` повторяют только
  занятый идентичный запуск и делят ожидание с прежним timeout проверки.
- What changed: общий `runCommand` и остальные вызывающие стороны не менялись.
- Evidence: обязательные 4 целевых теста с `-count=10` → PASS; `go vet
  ./internal/worker` и `git diff --check` → PASS.
- One next action: Verify выполняет один полный `go test ./... -count=1`.

## LOG

### 2026-08-12 — Specification

CARD-0061 ввела глобальный неблокирующий `flock` по executable, каноническому cwd
и argv. Все Claude-службы работают из `/opt/factory`, поэтому совпавший
`claude --version` или `claude auth status --json` сейчас даёт второй службе
`ErrCommandAlreadyRunning`, а `checkHealth` ошибочно объявляет её нездоровой.

Выбран локальный bounded retry только для command-probes в `checkHealth`.
Ожидание реагирует на cancel/deadline и не запускает второй одинаковый процесс;
любая иная ошибка возвращается немедленно. Изменение systemd cwd, ослабление
общей дедупликации, supervisor/task-команды и санитар CARD-0093 не входят в scope.

Критерий передачи в Implement: обязательная команда из спецификации должна
подтвердить два здоровых конкурентных Claude check, отсутствие второго процесса,
настоящую CLI-ошибку, ограниченный timeout и неизменный немедленный возврат
`ErrCommandAlreadyRunning` из общего `runCommand`.

### 2026-08-12 — Implement

`checkHealth` получил локальное context-aware ожидание только для
`ErrCommandAlreadyRunning`: конкурентные Claude probes теперь проходят
последовательно в рамках прежнего timeout, а общая дедупликация команд остаётся
неблокирующей. Четыре обязательных теста прошли десять раз подряд; отдельно
успешны `go vet ./internal/worker` и `git diff --check`.

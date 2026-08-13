# CARD-0098 — Конкурентные Claude health-probe ждут занятый probe

Implementation commit: b083860744997c99646b43a831a991e6df515d02 — health-check ограниченно ждёт совпадающую команду, не ослабляя общий неблокирующий запуск.

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/67deaa66-d9b-88731149-cea`.
- Implementation commit: b083860744997c99646b43a831a991e6df515d02 — health-check ограниченно ждёт совпадающую команду, не ослабляя общий неблокирующий запуск.
- Specification: `knowledge/specs/concurrent-claude-health-probes.md`.
- What changed: все короткие command-probe в `checkHealth` повторяют только
  занятый идентичный запуск и делят ожидание с прежним timeout проверки.
- What changed: общий `runCommand` и остальные вызывающие стороны не менялись.
- Evidence: три health-критерия с `-count=10` → PASS; `git diff --check` →
  PASS. Полный `go test ./... -count=1` завершился с двумя независимыми
  интеграционными группами: три controlplane manifest-сценария и worker pool
  refill; целевые health-тесты остаются зелёными.
- One next action: human merge после учёта известных нестабильных integration-тестов.

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

### 2026-08-12 — Verify

| Критерий | Проверка | Результат |
|---|---|---|
| Два одинаковых Claude health-probe не запускаются одновременно и оба становятся healthy | `go test ./internal/worker -run 'Test(ConcurrentClaudeHealthChecksWaitForIdenticalProbe|ClaudeHealthCheckPreservesCommandFailure|ClaudeHealthCheckLockWaitHonorsTimeout)$' -count=10` | PASS, 30/30 проверок |
| Ошибка CLI сохраняется, timeout ожидания ограничен | та же целевая команда | PASS |
| Общий `runCommand` остаётся неблокирующим | целевые health-тесты плюс проверка изменённых вызовов в `health.go` | PASS; код общего launcher не изменён |
| Полный проект без регрессий | `go test ./... -count=1` | НАХОДКА: FAIL в трёх `controlplane` manifest-сценариях и `TestCodexWorkerPoolRunsTenAttemptsAndRefillsReleasedSlot`; повтор worker-сценария также FAIL, вне изменённых health-файлов |
| Рабочее дерево и патч без ошибок форматирования | `git diff --check`, `git status --short` | PASS |

Pinned base: `e6c884a4387b92e3059d1385cc84a3bc22c95c3b`; candidate:
`08789a6fdb8e42e0acef9fc8711f4667c460a231`.

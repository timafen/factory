# CARD-0098 — Конкурентные Claude health-probe ждут занятый probe

## HEAD

- Status: Specification ready — awaiting Implement.
- Branch: `factory/5c09952f-39c-ef313de3-f45`.
- Specification: `knowledge/specs/concurrent-claude-health-probes.md`.
- Owner impact: исправные Claude-службы с общим `cwd=/opt/factory` не будут
  становиться `unhealthy` только из-за совпавших version/auth probes.
- Safety boundary: общий `runCommand` сохраняет немедленный
  `ErrCommandAlreadyRunning`; ограниченное ожидание разрешено только внутри
  health-check и делит его прежний timeout с выполняемой командой.
- Evidence required: конкурентный тест двух Claude health-check, отдельные
  проверки настоящей ошибки, timeout и прежней семантики CARD-0061.
- Next action: реализовать точный scope спецификации в `health.go` и
  `health_test.go`, затем записать сюда полный implementation commit.

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

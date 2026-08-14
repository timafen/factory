Implementation commit: dd3d7951e1afea8402849c72caf30c8aa4ba315c — определена проверяемая спецификация восстановления пропущенной передачи Pilot.

# CARD-0155 — Доиграть передачу этапа после рестарта Pilot

## HEAD

- Status: Specified — ожидает Implement + Test.
- Branch: `factory/e9e8177d-64c-610eb26c-6da`.
- What is defined: startup-reconciliation сверяет свежие successful terminal
  задачи из durable `processed` с фактическим хвостом через `live_or_done_at()`
  и передаёт обычному handoff только отсутствующий следующий этап.
- Safety boundary: durable watermark последнего успешного цикла, startup-снимок
  ID и lifecycle guards запрещают replay старой, закрытой, остановленной,
  failed/cancelled или финальной работы.
- Implementation scope: `pilot/pilot.py`, `pilot/test_pilot.py`.
- Required proof:
  `python3 -m unittest -q pilot.test_pilot.AdaptivePollingTests.test_restart_recovers_processed_success_with_missing_next_stage`.
- Specification: `knowledge/specs/pilot-terminal-handoff-recovery.md`.
- Next action: реализовать recovery и restart-regression без изменений UI,
  API/schema, release и независимых state machines.

## LOG

### 2026-08-14 — Specification

Зафиксирована точная граница свежести: terminal `finished_at`/`updated_at`
должен быть строго новее watermark последнего успешно сохранённого цикла;
первый запуск и задача без terminal timestamp историю не переигрывают.
Следующий или более поздний live/succeeded этап подавляет create, а временно
невозможная передача повторяется только в пределах startup-набора. Тест-план
отдельно покрывает один replay после restart, отсутствие дубля и все
запрещённые lifecycle-состояния.

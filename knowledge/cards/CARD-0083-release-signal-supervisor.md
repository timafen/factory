# CARD-0083 — Выпуск не зависает на сигналах остановки

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/8a355629-899-cb80a95e-8d5`.
- Implementation commit: 4587a9d7498c77e66252272898f5cdc80ca0ced2 — supervisor
  немедленно останавливает обе process groups и ограничивает reap по времени.
- What changed: блокирующий `wait -n` заменён отзывчивым supervisor; dispositions
  HUP/INT/TERM нормализуются, TERM эскалируется в KILL, после сигнала install закрыт.
- Evidence: `bash ops/test-fx-factory-release.sh` — PASS для пяти повторов каждого
  сигнала без процессов и установки; Go tests/build и UI tests/lint/build — PASS.
- Next action: человек принимает решение о слиянии.

## LOG

### 2026-08-11 — Implement

На ветке `factory/8a355629-899-cb80a95e-8d5` release-supervisor переведён с
неограниченного `wait -n` на polling, bounded reap и TERM→KILL обеих process
groups. Ранний self-exec восстанавливает SIGINT фонового job, а stop-флаг
запрещает переход к production install. Целевой тест по пять раз проверил
HUP/INT/TERM, верхнюю границу пять секунд, отсутствие потомков и установки;
реализация — `4587a9d7498c77e66252272898f5cdc80ca0ced2`.

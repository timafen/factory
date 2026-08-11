# CARD-0083 — Выпуск не зависает на сигналах остановки

## HEAD

- Status: Verified PASS — ready for Verify.
- Branch: `factory/65c76754-42f-f072ad5b-30e`.
- Implementation commit: 548d5e909a0676a94073cfa4a3ef2817ca9b1524 — выпуск
  проверяет process groups и добивает TERM-игнорирующих потомков через KILL.
- What changed: polling отслеживает process group, а не только launcher; после
  ограниченного ожидания KILL отправляется лишь существующим группам и launcher reap-ится.
- Evidence: `bash ops/test-fx-factory-release.sh` — PASS, включая UI и Go
  потомков, игнорирующих TERM, отсутствие процессов и production install.
- Next action: Verify выполняет полный Go/UI набор проверок.

## LOG

### 2026-08-11 — Implement

На ветке `factory/8a355629-899-cb80a95e-8d5` release-supervisor переведён с
неограниченного `wait -n` на polling, bounded reap и TERM→KILL обеих process
groups. Ранний self-exec восстанавливает SIGINT фонового job, а stop-флаг
запрещает переход к production install. Целевой тест по пять раз проверил
HUP/INT/TERM, верхнюю границу пять секунд, отсутствие потомков и установки;
реализация — `4587a9d7498c77e66252272898f5cdc80ca0ced2`.

### 2026-08-11 — Implement

На ветке `factory/65c76754-42f-f072ad5b-30e` устранён race: завершившийся
launcher больше не маскирует TERM-игнорирующего потомка в той же process group.
Перед KILL supervisor проверяет `kill -0 -- -PGID`, bounded-поллит исчезновение
групп и reap-ит launcher. `bash ops/test-fx-factory-release.sh` прошёл с
adversarial UI и Go потомками, подтвердив TERM→KILL, отсутствие потомков и
отсутствие production install; реализация — `548d5e909a0676a94073cfa4a3ef2817ca9b1524`.

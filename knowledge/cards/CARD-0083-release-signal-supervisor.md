# CARD-0083 — Выпуск не зависает на сигналах остановки

## HEAD

- Status: Verified PASS — ready for Verify.
- Branch: `factory/10f9d5f3-f5b-6c2ca72c-933`.
- Implementation commit: cf900fcd66d70d2bd72181e448ea57bbbd6e7260 — сигнал
  ограниченно ждёт PGID, затем останавливает pending launcher и его process group.
- What changed: регистрация launcher защищена от сигнала до PID readiness;
  stop-файл не даёт позднему setsid запустить test gate после остановки.
  Supervisor обнаруживает готовую группу, выполняет TERM→KILL и reap без неограниченного wait.
- Evidence: `bash ops/test-fx-factory-release.sh` — PASS для HUP/INT/TERM до
  readiness UI и Go, watchdog, TERM-ignoring потомков, отсутствия процессов/install;
  `go test ./...` и `bash scripts/test-build.sh` — PASS.
- Next action: Verify подтверждает delivery ветки и результаты регрессии.

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

### 2026-08-11 — Implement

На ветке `factory/10f9d5f3-f5b-6c2ca72c-933` устранено последнее окно до
записи PGID: pending launcher регистрируется до обработки сигнала, stop-файл
не даёт позднему setsid выполнить gate, а supervisor ограниченно ждёт группу,
останавливает launcher и применяет TERM→KILL/reap. `bash ops/test-fx-factory-release.sh`
прошёл для HUP/INT/TERM до readiness UI и Go с watchdog, отсутствием процессов
и production install; `go test ./...` и `bash scripts/test-build.sh` прошли;
реализация — `cf900fcd66d70d2bd72181e448ea57bbbd6e7260`.

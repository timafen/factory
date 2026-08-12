# CARD-0083 — Выпуск не зависает на сигналах остановки

## HEAD

- Status: Implemented — ready for repeated Review.
- Branch: `factory/32cba600-231-1808620a-969`.
Implementation commit: 6e3ecaa2db940c63a9b6e835f9ee95179f9da818 — сессия
  создаётся до intermediary launcher, fork setsid удерживается для reap.
- What changed: реальный SID/PGID проверяется до запуска UI/Go gate; ранняя
  остановка находит дочернего session leader и завершает всю группу.
- Evidence: `bash ops/test-fx-factory-release.sh` — PASS для HUP/INT/TERM,
  fork `setsid --wait`, intermediary UI/Go launcher, отсутствия процессов/install;
  `bash scripts/test-build.sh` — PASS. Общий Go-прогон имеет внешний сбой
  `TestTimeoutStopsIgnoringProcessGroup`, воспроизводимый без изменений Go-кода.
- Next action: Review повторно проверяет ранний сигнал с fork/intermediary launcher.

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

### 2026-08-11 — Implement

На ветке `factory/32cba600-231-1808620a-969` граница session перенесена перед
`$AS`: fork intermediary launcher остаётся в известном PGID, а `setsid --wait`
удерживает и reap-ит fork-ветку. Регрессия для UI и Go отправляет HUP/INT/TERM
после создания дочерней сессии, но до PGID-handshake, и подтверждает отсутствие
процессов и production install; реализация — `566e2fe26055c7a5b46946ed392450a153f716c8`.

### 2026-08-11 — Implement

После rebase на свежий `main` завершившийся session leader стал исчерпывать
watchdog как zombie до финального `wait`. Supervisor теперь сразу распознаёт и
reap-ит zombie launcher, а polling не рассылает TERM уже известному PGID.
Полный `bash ops/test-fx-factory-release.sh` прошёл в пределах пяти секунд на
каждую остановку; реализация — `6e3ecaa2db940c63a9b6e835f9ee95179f9da818`.

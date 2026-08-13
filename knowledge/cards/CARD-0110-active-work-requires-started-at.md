# CARD-0110 — «В работе прямо сейчас» только для начатых попыток

Implementation commit: ceeb326e11dc38e048aab703d26f08084442c761 — API задач различает подготовленную и фактически начатую попытку по `started_at`.

## HEAD

- Status: Implement + Test complete — awaiting Review.
- Branch: factory/062eebe4-55a-0a46bf1b-ac6
- Implementation commit: ceeb326e11dc38e048aab703d26f08084442c761
- What changed: сводный контракт задачи отдаёт `started_at` только для активной попытки; `preparing` больше не маскируется состоянием `running` до `StartAttempt`.
- Evidence: `TestTasksExposeAttemptStartedAtAndKeepPreparingQueued` — PASS; `go test ./internal/controlplane/... -count=1` — PASS (105.175s); `go build ./...` — PASS.
- Next action: проверить контракт и регрессию на этапе Review.

## LOG

### 2026-08-12 — Implement

В список задач добавлена дата старта текущей активной попытки. Подготовленная
попытка остаётся `preparing` с пустым `started_at`, а после `StartAttempt`
становится `running` с фактической датой; завершённые попытки к полю не
подмешиваются. Внутреннее чтение задач для возобновления pipeline приведено к
тому же контракту.

Проверено новым сценарием до/после старта, регрессиями resume, полным набором
`go test ./internal/controlplane/... -count=1`, сборкой `go build ./...` и
`git diff --check`.

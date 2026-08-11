# CARD-0048 — Санитар убирает фантомные worktree остановленного Claude-воркера

## HEAD

- Status: Implemented — awaiting human merge
- Branch: `factory/47f4cd8b-10f-cac304a5-7fd`
- Implementation commit: dd4990781ac69cf867eed7d159278e4248a3b51f — внутреннее
  подтверждение очистки retained worktree принимает запросы только с loopback.
- Specification: `knowledge/specs/offline-claude-haiku-retained-worktree.md`
- What changed: control plane по-прежнему снимает только точные подтверждённые
  снимки после карантина; новый маршрут теперь защищён прямым loopback-доступом,
  поэтому внешний запрос не может снять retained worktree.
- Evidence: `go test ./internal/controlplane` — PASS; `bash
  ops/test-factory-janitor.sh` — PASS.
- Next action: человеку влить ветку в `main`.

## LOG

### 2026-08-10 — Specification

Зафиксирован разрыв между файловой очисткой и снимком control plane: санитар
переносит worktree и manifest в карантин, однако `retained_worktrees_json` воркера
меняет только следующая регистрация самого воркера. Для остановленного
`claude-haiku` такой регистрации нет, поэтому API продолжает показывать фантом и
не даёт удалить связанную историю. Выбрано подтверждаемое удаление только
наблюдённых записей через control plane; полная перерегистрация санитаром не нужна.

### 2026-08-10 — Implement

Добавлен отдельный маршрут подтверждения санитарной очистки и транзакционное
точечное снятие снимков, поэтому повторный запуск не затрагивает новые либо
несовпадающие записи. Санитар передаёт в control plane только worktree, успешно
перемещённые в карантин. Изолированный shell-тест и тесты control plane проходят.

### 2026-08-10 — Verify

| Критерий | Команда / проверка | Результат |
|---|---|---|
| Перемещённый worktree исчезает из API | `TestHTTPClearRetainedWorktrees`; `bash ops/test-factory-janitor.sh` | PASS: в карантине файл есть, в clear payload только его snapshot, ответ API пуст. |
| `DeleteTask` разблокирован | `TestClearRetainedWorktreesUnblocksTerminalTaskDeletion` | PASS: до clear код `retained_worktree`, после clear удаление успешно. |
| Неперемещённое не подтверждается; HTTP-сбой виден | `bash ops/test-factory-janitor.sh` | PASS: несуществующий path не вошёл в payload; при exit 22 карантин сохранён и журнал пишет ошибку. |
| Точность и идемпотентность | `TestClearRetainedWorktreesRemovesOnlyConfirmedSnapshots` | PASS: несовпавший snapshot сохранён, повтор ничего не меняет. |
| Семантика регистрации сохранена | тот же store-тест; `TestWorkerRuntimeDeterminesExecutionAndCannotChange`; `TestRegistrationAcknowledgesSameMillisecondTerminalHandoff` | PASS: name/runtime/health/capacity/heartbeat не изменились; runtime и capacity handoff проходят старые регрессии. |

Полный CI-подобный прогон: `npm ci`, `just ui-check`, `just ui-build 0`,
`just build`, `just test-tooling`, `just test-release`, `just test-launcher`,
`just format-check`, `just vet`, `just vuln`, `just staticcheck`, `just boundary`,
`just test`, `just test-worker-race`, `just test-browser` и целевой shell-тест.
Все прошло, кроме уже существующих ошибок `staticcheck` в
`cards_http.go:37`/`pilot_config.go:136` и несвязанного browser-таймаута в
`control-plane.spec.ts:421`; все три файла вне diff задачи.

### 2026-08-11 — Implement

Маршрут подтверждения очистки retained worktree теперь отклоняет forwarded и
внешние запросы той же loopback-проверкой, что и регистрация воркера. Тест
`TestHTTPClearRetainedWorktreesRequiresDirectLoopback` подтверждает ответ 403;
`go test ./internal/controlplane` и `bash ops/test-factory-janitor.sh` проходят.

### 2026-08-11 — Card repair

Исправлена ссылка на реализацию: прежний хеш был из эквивалентной, но другой
ветки. В этой ветке loopback-защиту маршрута добавляет
`dd4990781ac69cf867eed7d159278e4248a3b51f`; хеш является предком ветки и меняет
`internal/controlplane/http.go` вместе с его тестом.

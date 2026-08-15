# GitHub CLI в рабочем checkout использует origin задачи

## Цель и влияние на владельца

Агент в Factory-worktree должен выполнять команды GitHub CLI над репозиторием
текущей задачи, даже когда в checkout одновременно присутствуют
`origin=timafen/factory` и `upstream=owainlewis/factory`. Наблюдаемый checkout
без `GH_REPO` воспроизводит риск: локальная настройка
`remote.upstream.gh-resolved=base` заставляет bare-команду `gh repo view`
вернуть `owainlewis/factory`.

Для владельца требуемый результат — чтение и запись GitHub всегда направлены в
`timafen/factory`, назначенный задаче. Исправление не переименовывает remote-ы,
не меняет их URL, tracking веток или пользовательскую конфигурацию `gh`.

## Технический подход и реальные файлы

Доверенный источник контекста — `claim.Repository.RemoteIdentity`, а не выбор
remote-а самим GitHub CLI. В `internal/worker/attempt_lifecycle.go`
`Manager.runAttempt` передаёт identity в сериализованный `supervisorInit`.
Общий для Codex и Claude Code конструктор `runtimeEnvironment` в
`internal/worker/supervisor.go` сначала удаляет любой унаследованный `GH_REPO`,
а затем добавляет ровно один `GH_REPO=<owner>/<repository>` только для
валидной identity `github.com/<owner>/<repository>`.

Таким образом, `github.com/timafen/factory` даёт
`GH_REPO=timafen/factory`, и `gh` не выбирает конфликтующий upstream.
Host распознаётся без учёта регистра, owner и repository нормализуются в
нижний регистр существующим `normalizeManagedGitHubIdentity`. Пустая,
некорректная, файловая, GitLab или неизвестная self-hosted identity не получает
`GH_REPO`, включая унаследованное чужое значение.

Реальные файлы реализации:

- `internal/worker/attempt_lifecycle.go` — передача identity из claim в
  supervisor;
- `internal/worker/supervisor.go` — единая политика runtime environment;
- `internal/worker/supervisor_environment_test.go` — матрица допустимых и
  отклоняемых identity;
- `internal/worker/worker_integration_test.go` — сквозная проверка фактического
  окружения дочернего процесса.

Код этого контракта уже находится в свежем `origin/main` в коммите
`fee29b0c65cc12058cc8c08d6ad87855367bdec8`. Эта работа документирует
наблюдаемый случай и не требует повторного изменения продуктового кода.

## Последовательный план

1. Передать `claim.Repository.RemoteIdentity` в `supervisorInit` до запуска
   дочернего runtime.
2. При формировании environment всегда удалить прежний `GH_REPO`.
3. Провалидировать GitHub.com identity и добавить единственное нормализованное
   значение; для недоверенной identity оставить переменную отсутствующей.
4. Сохранить существующую изоляцию service-only `FACTORY_*`, локальный
   `.factory-build` и locale `C.UTF-8`.
5. Подтвердить полный путь claim → manager → supervisor → fake Codex целевым
   тестом, а политику входов — отдельной табличной регрессией.

## Критерии приёмки

- При `origin=timafen/factory`, `upstream=owainlewis/factory` и claim identity
  `github.com/timafen/factory` дочерний runtime получает ровно
  `GH_REPO=timafen/factory`.
- Унаследованный `GH_REPO=owainlewis/factory` не виден дочернему процессу и не
  может переопределить репозиторий задачи.
- Codex и Claude Code получают одинаковую политику через общий конструктор
  environment.
- Для invalid, file, GitLab и неизвестного self-hosted хоста `GH_REPO`
  отсутствует; недостоверное значение не угадывается из remote-ов.
- `origin`, `upstream`, их URL и refspec, tracking веток, global config `gh`,
  control plane и UI остаются без изменений.
- Целевой сквозной тест завершается с кодом 0.

## Тест-план

`TestRuntimeEnvironmentGitHubRepositoryPolicy` в
`internal/worker/supervisor_environment_test.go` проверяет нормализацию
валидного GitHub.com, отрицательную матрицу и отсутствие дублей `GH_REPO`.

`TestWorkerRuntimeUsesClaimGitHubRepositoryContext` в
`internal/worker/worker_integration_test.go` задаёт supervisor чужой
`GH_REPO=owainlewis/factory`, создаёт claim `github.com/example/cattle` и
запускает реальный путь manager → supervisor → fake Codex. Fake runtime
завершается успешно только при точном `GH_REPO=example/cattle`; это проверяет
не только построение массива, но и окружение процесса.

Итерационная обязательная проверка — только этот сквозной тест. На отдельном
этапе Verify допустимо дополнительно выполнить `go test -count=1
./internal/worker` и `git diff --check`.

## Риски и решения

- **Выбор upstream самим `gh`.** Передавать `GH_REPO` из claim, не полагаться на
  `remote.*.gh-resolved` или текущий каталог.
- **Чужое значение из окружения сервиса.** Всегда фильтровать `GH_REPO` перед
  условным добавлением вычисленного значения.
- **Ложное распознавание GitHub Enterprise.** Разрешать только `github.com`,
  пока claim не переносит доверенные provider и hostname.
- **Разное поведение runtime-ов.** Формировать environment в общем пути запуска
  Codex и Claude Code.
- **Старый уже запущенный worker.** Переменная появляется только у новых
  supervisor-процессов из сборки с реализацией; выпуск и перезапуск относятся к
  штатной доставке, а не к изменению remote-ов в этой работе.

## Карточка работы

Карточка: `knowledge/cards/CARD-0301-current-checkout-github-origin-context.md`.

`CARD-0300` уже занят опубликованной параллельной работой. Номер и путь
`CARD-0301` отсутствовали в свежем `origin/main` и во всех опубликованных
ветках `origin` на момент подготовки этой спецификации.

ГОТОВО-КОГДА: файл internal/worker/attempt_lifecycle.go
ГОТОВО-КОГДА: файл internal/worker/supervisor.go
ГОТОВО-КОГДА: файл internal/worker/supervisor_environment_test.go
ГОТОВО-КОГДА: файл internal/worker/worker_integration_test.go
ГОТОВО-КОГДА: команда go test -count=1 ./internal/worker -run '^TestWorkerRuntimeUsesClaimGitHubRepositoryContext$'

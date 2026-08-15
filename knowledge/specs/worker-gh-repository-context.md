# Worker закрепляет GitHub CLI за репозиторием задачи

## Цель и влияние на владельца

Агент в назначенном worktree должен выполнять неявные команды GitHub CLI
(`gh repo view`, `gh pr view`, `gh issue create` и другие команды без `--repo`)
над репозиторием текущей задачи. Сейчас runtime наследует окружение без
закреплённого репозитория, поэтому `gh` может выбрать `upstream` или ранее
настроенный default и обратиться к чужому проекту. Для владельца исправление
устраняет риск чтения или изменения не того GitHub-репозитория без изменения
remote-ов worktree.

## Технический подход и реальные файлы

Источник истины — `claim.Repository.RemoteIdentity`, уже доступный в
`Manager.runAttempt` в `internal/worker/attempt_lifecycle.go`. В
`supervisorInit` из `internal/worker/supervisor.go` добавить поле remote
identity и передавать в него именно значение из claim. Supervisor должен
получить поле через существующий JSON-контракт и передать его в общий
конструктор `runtimeEnvironment`, используемый и Codex, и Claude Code.

При каждом формировании runtime environment сначала удалять унаследованный
`GH_REPO`. Если remote identity имеет ровно каноническую структуру
`github.com/<owner>/<repository>` и owner/repository проходят уже существующие
worker-правила `validGitHubOwner` и `validGitHubRepository`, добавить один
`GH_REPO=<owner>/<repository>`. Значение нормализовать так же, как managed
GitHub identity: host распознаётся без учёта регистра, owner и repository
приводятся к нижнему регистру. Для `github.com/timafen/factory` результат
обязан быть ровно `GH_REPO=timafen/factory`. Это соответствует документированному
GitHub CLI формату `[HOST/]OWNER/REPO`: [gh environment](https://cli.github.com/manual/gh_help_environment).

Для пустой, некорректной, файловой или не-GitHub identity переменная должна
отсутствовать, даже если сервис-воркер унаследовал чужой `GH_REPO`. Нельзя
сохранять недостоверное значение и нельзя угадывать провайдера по произвольному
FQDN.

Self-hosted GitHub в этой работе намеренно не получает `GH_REPO`. GitHub CLI
поддерживает `HOST/OWNER/REPO`, но текущий `protocol.Claim` содержит только
remote identity и не переносит `TaskRoute.SourceAccess`, поэтому worker не
может отличить GitHub Enterprise Server от GitLab/Gitea на том же формате
`host/owner/repo`. Поддержка self-hosted GitHub требует отдельного протокольного
изменения с доверенными provider и hostname; тогда допустимым результатом
станет `GH_REPO=<host>/<owner>/<repository>`. `GH_HOST` в этой работе не
добавляется.

Существующая Factory-изоляция в `runtimeEnvironment` остаётся неизменной:
service-only `FACTORY_*` удаляются, `FACTORY_BUILD_DIR` направляется в
`.factory-build` worktree, обычные runtime-переменные сохраняются, а
`LANG`/`LC_ALL` остаются `C.UTF-8`. Единственное новое исключение среди обычных
переменных — `GH_REPO`, который всегда удаляется и затем при доказанной
GitHub.com identity добавляется ровно один раз.

Реальные файлы будущей реализации:

- `internal/worker/attempt_lifecycle.go` — перенести remote identity claim в
  supervisor init;
- `internal/worker/supervisor.go` — расширить init-контракт, валидировать
  identity и сформировать runtime environment;
- `internal/worker/supervisor_environment_test.go` — проверить матрицу
  валидных, некорректных и не-GitHub identity вместе с Factory-изоляцией;
- `internal/worker/worker_integration_test.go` — запустить runtime через
  manager/claim/supervisor и проверить точное значение `GH_REPO`.

Не входят в работу: изменение `origin`/`upstream`, вызов `gh repo set-default`,
глобальная конфигурация GitHub CLI, `GH_HOST`, control plane, UI и поведение
конкретных GitHub-команд.

## Последовательный план

1. Добавить remote identity в `supervisorInit` и заполнить её из
   `claim.Repository.RemoteIdentity` при запуске попытки.
2. Изменить сигнатуру `runtimeEnvironment`, чтобы она принимала remote
   identity, всегда фильтровала унаследованный `GH_REPO` и добавляла вычисленное
   значение только для валидного `github.com/owner/repository`.
3. Переиспользовать существующие ограничения owner/repository, не вводя второй
   расходящийся синтаксис GitHub identity.
4. Обновить существующий тест Factory-изоляции под новый вход и добавить
   табличный тест политики: валидный GitHub.com, пустое значение, malformed
   identity, `file://`, GitLab и произвольный self-hosted FQDN.
5. Добавить worker integration test с исходным чужим `GH_REPO`, валидным
   GitHub claim и fake Codex, который завершается успешно только при точном
   `GH_REPO` назначенного репозитория.

## Критерии приёмки

- Полный путь `claim -> supervisor init -> runtime process` преобразует
  `github.com/example/cattle` в единственную переменную
  `GH_REPO=example/cattle`.
- Унаследованный `GH_REPO=owainlewis/factory` не виден runtime и заменён
  значением репозитория задачи до запуска Codex или Claude Code.
- Для пустой identity, неправильного числа сегментов, недопустимого
  owner/repository, `file://`, GitLab и неизвестного/self-hosted хоста
  `GH_REPO` отсутствует; чужое унаследованное значение также не сохраняется.
- Одинаковый конструктор environment обслуживает оба runtime, поэтому политика
  не зависит от выбора Codex или Claude Code.
- Тест `TestRuntimeEnvironmentIsolatesAgentBuildsFromLiveFactory` продолжает
  доказывать удаление service-only Factory-переменных, локальный
  `.factory-build`, сохранение обычной sentinel-переменной и UTF-8 locale.
- Аргументы runtime, cwd, prompt, timeout, process group, Git remotes, worker
  registration/control plane и UI не меняются.

## Тест-план

В `internal/worker/worker_integration_test.go` добавить
`TestWorkerRuntimeUsesClaimGitHubRepositoryContext`. Тест должен:

1. Установить в окружении supervisor заведомо чужой
   `GH_REPO=owainlewis/factory`.
2. Создать/назначить задачу репозиторию с claim identity
   `github.com/example/cattle` и запустить реальный путь manager → supervisor →
   fake Codex.
3. Потребовать в fake runtime точное `GH_REPO=example/cattle`, а не просто
   наличие переменной; при другом значении runtime возвращает ненулевой код.
4. Дождаться успешного terminal state задачи. Так тест одновременно доказывает
   передачу identity из claim, перезапись наследования и фактическое окружение
   дочернего процесса.

В `internal/worker/supervisor_environment_test.go` добавить
`TestRuntimeEnvironmentGitHubRepositoryPolicy` с табличными отрицательными
случаями и проверкой отсутствия дублей `GH_REPO`. Существующий
`TestRuntimeEnvironmentIsolatesAgentBuildsFromLiveFactory` оставить отдельной
регрессией границы Factory-переменных.

Итерационная обязательная проверка — только новый сквозной тест. Перед Verify
дополнительно выполнить `go test -count=1 ./internal/worker` и
`git diff --check`; полный проектный набор относится к отдельной стадии Verify.

## Риски и решения

- **Подмена через унаследованное окружение.** Всегда фильтровать `GH_REPO` до
  условного добавления вычисленного значения; не применять append поверх
  `os.Environ()` без удаления старой записи.
- **Ложное распознавание self-hosted сервиса как GitHub.** Разрешить только
  `github.com`; расширять список хостов лишь после появления доверенного
  provider/hostname в claim.
- **Расхождение валидаторов.** Переиспользовать worker-правила owner/repository
  и покрыть нормализацию регистра тестом.
- **Ослабление Factory-изоляции при изменении сигнатуры.** Сохранить отдельный
  существующий тест всех заблокированных `FACTORY_*`, build-dir и locale.
- **Потеря контекста после рестарта supervisor.** Remote identity является
  частью сериализованного `supervisorInit`, поэтому дочерний процесс не зависит
  от локального Git remote selection.

## Карточка работы

Карточка: `knowledge/cards/CARD-0167-worker-gh-repository-context.md`.

Номер `CARD-0164`, предложенный на Triage, уже занят опубликованной работой
`CARD-0164-stage-attempts-passed-snapshot`; `CARD-0165` и `CARD-0166` также
заняты в опубликованных ветках. `CARD-0167` и выбранный путь отсутствуют в
свежем `origin/main` и проверенных опубликованных refs.

ГОТОВО-КОГДА: файл knowledge/specs/worker-gh-repository-context.md
ГОТОВО-КОГДА: файл knowledge/cards/CARD-0167-worker-gh-repository-context.md
ГОТОВО-КОГДА: файл internal/worker/attempt_lifecycle.go
ГОТОВО-КОГДА: файл internal/worker/supervisor.go
ГОТОВО-КОГДА: файл internal/worker/supervisor_environment_test.go
ГОТОВО-КОГДА: файл internal/worker/worker_integration_test.go
ГОТОВО-КОГДА: команда go test -count=1 ./internal/worker -run '^TestWorkerRuntimeUsesClaimGitHubRepositoryContext$'

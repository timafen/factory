# Рабочий checkout направляет GitHub CLI в origin задачи

## Цель и влияние на владельца

Каждый агент, запущенный в рабочем checkout, должен считать `origin` целевым
GitHub-репозиторием задачи при неявных вызовах GitHub CLI. Наблюдаемая ошибка
показывает риск: при наличии `upstream=owainlewis/factory` команда `gh` без
`--repo` может выбрать upstream вместо `origin=timafen/factory`. Владельцу это
даёт предсказуемые чтение и запись в репозитории задачи и не меняет remote-ы
checkout или глобальную настройку пользователя.

## Технический подход и реальные файлы

`claim.Repository.RemoteIdentity` — единственный доверенный источник
репозитория. `Manager.runAttempt` в
`internal/worker/attempt_lifecycle.go` передаёт его в сериализованный
`supervisorInit` из `internal/worker/supervisor.go`. Общий для Codex и Claude
Code `runtimeEnvironment` удаляет унаследованный `GH_REPO`, затем только для
валидной identity `github.com/<owner>/<repository>` добавляет ровно одну
переменную `GH_REPO=<owner>/<repository>`.

Так `github.com/timafen/factory` становится `GH_REPO=timafen/factory`, и GitHub
CLI использует именно репозиторий задачи, не выбирая `upstream`. Owner и
repository валидируются существующими правилами worker; host сравнивается без
учёта регистра, owner/repository нормализуются в нижний регистр. Пустая,
некорректная, файловая, GitLab и неизвестная self-hosted identity не дают
`GH_REPO`: без доверенного provider нельзя отличить GitHub Enterprise от
другого хоста. `GH_HOST`, `gh repo set-default`, изменение remote-ов и UI вне
работы.

Реальные файлы реализации:

- `internal/worker/attempt_lifecycle.go`;
- `internal/worker/supervisor.go`;
- `internal/worker/supervisor_environment_test.go`;
- `internal/worker/worker_integration_test.go`.

## Последовательный план

1. Передать remote identity из claim в `supervisorInit` до старта дочернего
   runtime.
2. Сформировать environment в одном месте: убрать прежний `GH_REPO`, добавить
   вычисленный только после валидации GitHub.com identity.
3. Сохранить существующую изоляцию `FACTORY_*`, `.factory-build` и locale
   `C.UTF-8`.
4. Закрепить политику табличным unit-тестом и сквозным тестом manager →
   supervisor → fake Codex.

## Критерии приёмки

- При claim `github.com/timafen/factory` runtime получает единственный
  `GH_REPO=timafen/factory`, даже если окружение supervisor содержало
  `GH_REPO=owainlewis/factory`.
- Codex и Claude Code получают одну и ту же политику environment.
- Для invalid, file, GitLab и неизвестного self-hosted хоста `GH_REPO`
  отсутствует; унаследованное значение не протекает.
- Remote `origin` и `upstream`, глобальный GitHub CLI config, control plane и
  UI не меняются.

## Тест-план

`TestRuntimeEnvironmentGitHubRepositoryPolicy` покрывает валидный GitHub.com,
нормализацию регистра и отрицательную матрицу, включая отсутствие дублей.
`TestWorkerRuntimeUsesClaimGitHubRepositoryContext` запускает fake Codex с
чужим `GH_REPO` и завершается успешно лишь при точном
`GH_REPO=example/cattle`. Это доказывает полный путь claim → supervisor →
дочерний процесс, а не только построение массива environment.

## Риски и решения

- **Чужой контекст из окружения.** Всегда фильтровать `GH_REPO` до добавления
  вычисленного значения.
- **Ложный GitHub Enterprise.** Разрешать только `github.com`, пока claim не
  переносит доверенный provider и hostname.
- **Регрессия изоляции worker.** Оставить отдельный тест service-only
  `FACTORY_*`, build-dir и locale.
- **Обход общей политики runtime.** Вычислять environment в общем конструкторе,
  а не в ветке конкретного агента.

## Карточка работы

Карточка: `knowledge/cards/CARD-0300-working-checkout-origin-target-github-repository.md`.

Номер и путь `CARD-0300` отсутствовали в свежем `origin/main` и во всех
опубликованных ветках `origin` на момент подготовки спецификации.

ГОТОВО-КОГДА: файл internal/worker/attempt_lifecycle.go
ГОТОВО-КОГДА: файл internal/worker/supervisor.go
ГОТОВО-КОГДА: файл internal/worker/supervisor_environment_test.go
ГОТОВО-КОГДА: файл internal/worker/worker_integration_test.go
ГОТОВО-КОГДА: команда go test -count=1 ./internal/worker -run '^TestWorkerRuntimeUsesClaimGitHubRepositoryContext$'

# Bare-команды GitHub CLI используют `upstream` исходного репозитория

## Цель и влияние на владельца

Во всех рабочих копиях, которые Factory создаёт для управляемого GitHub-репозитория,
команды `gh` без явного аргумента репозитория должны работать с проектом задачи.
Например, в рабочей копии Factory команда `gh repo view --json nameWithOwner`
должна вернуть `owainlewis/factory`, то есть репозиторий, подключённый как `upstream`.
Это устраняет необходимость помнить явный slug в автоматизациях и не изменяет
Git-remote, tracking-ветки или выбор базовой ветки.

Решение владельца: `owainlewis/factory` — GitHub CLI default для рабочих копий
Factory; `timafen/factory` сохраняется как origin рабочего проекта.

## Технический подход и реальные файлы

Кэш управляемого репозитория создаётся в
`internal/worker/repository_cache.go`: `cloneManagedRepository` вызывает
`gh repo clone`, проверяет полученный `origin` и только затем атомарно переносит
клон в кэш. Рабочая копия позднее создаётся из этого кэша функцией
`addPreparedWorktree` в `internal/worker/git.go`, поэтому настройку нужно
записать в кэш после проверки `origin`, но до `os.Rename` и до первого worktree.

Реализация добавляет локальную Git-конфигурацию: удаляет все значения
`remote.origin.gh-resolved`, затем назначает `remote.upstream.gh-resolved=base`.
Она должна использовать существующий ограниченный запуск Git и возвращать
контекстную ошибку при невозможности прочитать или записать конфигурацию.
Remote URL, `remote.*.fetch`, branch tracking и содержимое checkout не меняются.
Уже существующий кэш также проходит эту идемпотентную настройку перед
`resolveRepository`, чтобы правило действовало для каждой созданной рабочей
копии, а не только для нового clone.

Целевая регрессия находится в
`internal/worker/repository_coordination_test.go`. Fixture создаст кэш с
конфликтующим `remote.origin.gh-resolved=base`, получит репозиторий через
`acquireManagedRepository`, затем в созданной worktree запустит bare
`gh repo view --json nameWithOwner`. Поддельный `gh` прочитает локальную
конфигурацию и вернёт slug `upstream`; проверка ожидает `owainlewis/factory` и
подтверждает, что `upstream` и Git tracking остались нетронутыми.

## Последовательный план

1. Вынести в `repository_cache.go` малую идемпотентную настройку GitHub CLI для
   пути кэша: снять `gh-resolved` с `origin`, назначить его `upstream`.
2. Вызывать её и после нового clone, и при повторном использовании существующего
   кэша, до выдачи репозитория для создания worktree.
3. Расширить fixture и добавить целевой интеграционный сценарий bare-команды
   `gh` в worktree с конфликтующим origin.
4. Запустить целевой Go-тест и проверить отсутствие непреднамеренных изменений
   remotes и tracking в его утверждениях.

## Критерии приёмки

- Новый кэш с `upstream=owainlewis/factory` создаёт worktree, где bare
  `gh repo view --json nameWithOwner` возвращает `owainlewis/factory`.
- Конфликтующее `remote.origin.gh-resolved=base` удалено; у `upstream` есть
  `gh-resolved=base`.
- Повторное получение уже созданного кэша даёт тот же результат.
- URL remotes, `remote.origin.fetch`, базовая ветка и Git tracking не меняются.
- Ошибка Git-конфигурации не выдаёт кэш или worktree как успешно подготовленные.

## Тест-план

Основной тест: `TestManagedRepositoryCacheSetsGitHubDefaultRepository` в
`internal/worker/repository_coordination_test.go` создаёт origin/upstream,
моделирует прежний конфликт и проверяет фактический JSON-ответ bare `gh` в
worktree. В нём же проверяются конфигурационные ключи и неизменность Git remotes
и tracking. Дополнительно существующие сценарии managed-cache запускаются вместе
с этим тестом, чтобы убедиться, что повторное использование кэша остаётся
безопасным.

## Риски и решения

- GitHub CLI хранит эвристику выбора репозитория в локальном Git config; запись
  не в том каталоге не попадёт в worktree. Решение: конфигурировать общий кэш до
  `git worktree add`.
- У проекта может быть легитимный `origin` для обычных Git-операций. Решение:
  удалить только `remote.origin.gh-resolved`, не трогая URL, refspec или
  tracking.
- Старые кэши переживают обновление воркера. Решение: выполнять настройку и для
  существующего кэша; операции unset/set должны быть идемпотентны.
- Неудавшаяся конфигурация может оставить неполный clone. Решение: сохранять
  текущую временную- и rename-схему и прекращать acquisition до установки кэша.

## Карточка работы

Связанная карточка: `knowledge/cards/CARD-0167-gh-default-repository.md`.
Она фиксирует границы: только подготовка кэша и целевой worker-тест; UI,
содержимое remotes и Git tracking не входят в работу.

## Проверяемая граница реализации

ГОТОВО-КОГДА: файл internal/worker/repository_cache.go
ГОТОВО-КОГДА: файл internal/worker/repository_coordination_test.go
ГОТОВО-КОГДА: команда go test ./internal/worker -run '^TestManagedRepositoryCacheSetsGitHubDefaultRepository$'

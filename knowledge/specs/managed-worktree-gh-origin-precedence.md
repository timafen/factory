# `gh` сохраняет зарегистрированный `origin` в управляемой рабочей копии

## Цель и влияние на владельца

Управляемая рабочая копия должна получать код именно из репозитория, который
зарегистрирован в Factory. Сейчас `gh repo clone` может оставить `upstream` как
приоритетный удалённый репозиторий; последующая проверка и получение базовой
ветки обращаются не к зарегистрированному `origin`. Владелец рискует запустить
работу на чужом коде либо получить ошибку уже после создания кэша.

После изменения Factory явно закрепляет зарегистрированный GitHub URL за
`origin` сразу после клонирования. `upstream`, если он добавлен `gh`, не влияет
на идентичность, поиск default branch и fetch базовой ветки.

## Технический подход и реальные файлы

- `internal/worker/repository_cache.go`: после успешного `gh repo clone` до
  `resolveRepository` привести remote `origin` к каноническому URL
  `https://github.com/<owner>/<repository>.git`. Если `origin` отсутствует,
  создать его; если существует с иным URL, заменить URL. Ошибку команды вернуть
  как ошибку получения managed repository и не устанавливать кэш.
- `internal/worker/worker_integration_test.go`: расширить сценарий
  `TestZeroRepositoryWorkerAcquiresCentrallyManagedGitHubRepository` (либо
  выделить равнозначный узкий тест), чтобы двойник `gh` создавал `upstream` с
  доступным репозиторием и оставлял неверный `origin`. Проверить, что worker
  завершает работу, кэш имеет зарегистрированный `origin`, а `upstream` не
  использован для определения базы.

Не меняются API, схема БД, настройки зарегистрированного репозитория и
обычные (не centrally managed) рабочие копии.

## Последовательный план

1. Добавить небольшую операцию нормализации `origin` в путь сразу после clone.
2. Сформировать URL только из уже проверенного `slug`, без входа пользователя
   в shell и без выбора URL по списку remotes.
3. Отличать отсутствие `origin` от ошибки Git: в первом случае добавить remote,
   во втором — прекратить получение с диагностикой.
4. Сделать регрессионный двойник `gh`, который воспроизводит наличие
   `upstream` и неверного `origin`.
5. Проверить выбранную базовую ветку, успешный task и то, что кэш остаётся
   связанным с `github.com/example/cattle`.

## Критерии приёмки

1. После `gh repo clone` у managed cache есть `origin` с URL зарегистрированного
   GitHub slug, независимо от remotes, оставленных `gh`.
2. Default branch и её commit разрешаются через этот `origin`, а не через
   `upstream`.
3. Клон с `upstream` и неверным либо отсутствующим `origin` проходит обычный
   managed-task flow только после нормализации `origin`.
4. Ошибка добавления или замены `origin` не публикует недействительный cache
   entry и возвращается как ошибка acquisition.
5. Существующий путь, где `gh` уже создаёт правильный `origin`, сохраняет
   успешное поведение.

## Тест-план

- Целевой Go-тест запускает managed acquisition с фальшивыми `gh` и `git`;
  `gh` оставляет `upstream` доступным, а зарегистрированный URL доступен только
  после нормализации `origin`.
- В тесте проверить URL `origin`, выбранные `BaseBranch` и `BaseCommit`, а также
  успешное завершение направленной работы.
- Отдельно покрыть ошибку `git remote add/set-url`, если изменение вынесено в
  helper.
- Обязательная команда: `go test ./internal/worker -run '^TestZeroRepositoryWorkerAcquiresCentrallyManagedGitHubRepository$'`.

## Риски и решения

- `gh` может добавить полезный `upstream` для fork. Его не нужно удалять:
  Factory использует только зарегистрированный `origin`, а дополнительный remote
  остаётся без влияния на выполнение.
- Нельзя доверять URL, сообщённому `gh`: ожидаемый URL строится из
  `normalizeManagedGitHubIdentity`, которая уже валидирует owner и repository.
- Нормализация должна случиться до `resolveRepository`, иначе текущая проверка
  identity откажет корректному заданию до возможности исправить remote.
- Не следует менять общую `resolveRepository`: она обслуживает legacy
  repositories и её расширение изменило бы область дефекта.

## Карточка работы

`knowledge/cards/CARD-0164-managed-worktree-gh-origin-precedence.md`

ГОТОВО-КОГДА: файл internal/worker/repository_cache.go
ГОТОВО-КОГДА: файл internal/worker/worker_integration_test.go
ГОТОВО-КОГДА: команда go test ./internal/worker -run '^TestZeroRepositoryWorkerAcquiresCentrallyManagedGitHubRepository$'

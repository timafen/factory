# Спецификация: CARD-0093 и первопричина ложного `unhealthy`

## Цель и влияние на владельца

Зафиксировать, что CARD-0093 и исправление ложного `unhealthy` решают разные
сбои. CARD-0093 уже запрещает санитару делать холостой stop/start для
online/unhealthy Claude. Первопричина ложного состояния — конкурентный
одинаковый health-probe, получающий `ErrCommandAlreadyRunning`, — закрыта в
CARD-0098. Поэтому CARD-0093 не является дубликатом и не требует новой
реализации; CARD-0098 должна отдельно пройти Verify по своему HEAD.

Владелец получает две независимые гарантии: санитар не перезапускает живого
online/unhealthy worker, а краткое совпадение Claude-проверок не объявляет
исправную службу нездоровой и не лишает её новых работ.

## Технический подход и реальные файлы

Фактическая реализация находится в свежем `origin/main` в коммите
`9af274d8` (со словесной подписью: неблокирующая дедупликация команд и
ожидание занятого health-probe). `internal/worker/health.go` использует
локальный `runHealthCommand`: только `ErrCommandAlreadyRunning` повторяется с
коротким context-aware ожиданием, в пределах прежнего timeout; остальные
ошибки и parsing остаются ошибками здоровья. Общий `runCommand` сохраняет
немедленную неблокирующую семантику.

Регрессии находятся в `internal/worker/health_test.go`: две конкурентные
Claude-проверки ждут lock без второго процесса, настоящая ошибка команды не
повторяется, а ожидание ограничивается deadline. Санитарный сценарий CARD-0093
остаётся в `ops/test-factory-janitor.sh` и проверяет отсутствие stop/start для
online/unhealthy worker; его scope не расширяется.

## Последовательный план

1. Передать предложение о первопричине в существующую
   `knowledge/cards/CARD-0098-concurrent-claude-health-probes.md`; новую
   карточку и новую реализацию не создавать.
2. Сверить реализацию и целевые тесты CARD-0098 с `origin/main`.
3. На Verify выполнить обязательную целевую Go-команду ниже по HEAD CARD-0098.
4. Оставить CARD-0093 самостоятельной карточкой санитаря, без пометки
   дубликатом и без изменений её продуктового scope.

## Критерии приёмки

- CARD-0093 явно остаётся отдельной работой: online/unhealthy Claude не
  получает stop/start или новую попытку резервирования.
- Два конкурентных одинаковых Claude health-check завершаются `healthy`, при
  этом одновременно существует не более одного процесса точной команды.
- `runCommand` для обычных вызывающих сторон по-прежнему сразу возвращает
  распознаваемый `ErrCommandAlreadyRunning`.
- Ожидание health lock учитывает общий deadline; отмена не запускает новый
  процесс и возвращает `unhealthy`.
- Ошибка CLI, пустой/невалидный ответ и `loggedIn=false` не маскируются retry.
- Новая карточка и новый продуктовый код для CARD-0093 не появляются.

## Тест-план

- Выполнить `go test ./internal/worker -count=1 -run
  '^(TestConcurrentClaudeHealthChecksWaitForIdenticalProbe|TestClaudeHealthCheckPreservesCommandFailure|TestClaudeHealthCheckLockWaitHonorsTimeout|TestRunCommandSkipsConcurrentDuplicate)$'`.
- Для санитаря использовать существующий `bash ops/test-factory-janitor.sh`
  только при Verify CARD-0093; этот этап Specification код не меняет.
- Проверить `git diff --check` и убедиться, что diff содержит только эту
  спецификацию.

## Риски и решения

- Смешение двух работ может привести к повторной реализации или ошибочной
  пометке дубликата. Решение: CARD-0093 документирует санитарный guard, а
  CARD-0098 владеет исправлением health-probe.
- Verify CARD-0098 может быть выполнен не на том HEAD. Решение: проверять
  именно HEAD карточки и фиксировать результат в её собственном Verify.
- Расширение retry на `runCommand` скроет реальные конфликты. Решение:
  retry ограничен `health.go` и только `ErrCommandAlreadyRunning`.

## Карточка работы

Текущая карточка: `knowledge/cards/CARD-0093-claude-janitor-skips-online-unhealthy.md`.
Связанная карточка первопричины: `knowledge/cards/CARD-0098-concurrent-claude-health-probes.md`.
Она уже содержит Implementation commit и ожидает отдельного Verify. В рамках
этой спецификации карточки не изменяются и новая карточка не создаётся.

ГОТОВО-КОГДА: файл internal/worker/health.go
ГОТОВО-КОГДА: файл internal/worker/health_test.go
ГОТОВО-КОГДА: файл knowledge/cards/CARD-0098-concurrent-claude-health-probes.md
ГОТОВО-КОГДА: команда go test ./internal/worker -count=1 -run '^(TestConcurrentClaudeHealthChecksWaitForIdenticalProbe|TestClaudeHealthCheckPreservesCommandFailure|TestClaudeHealthCheckLockWaitHonorsTimeout|TestRunCommandSkipsConcurrentDuplicate)$'

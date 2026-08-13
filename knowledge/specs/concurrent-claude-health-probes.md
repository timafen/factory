# Спецификация: конкурентные Claude health-probe ждут занятую команду

## Цель и влияние на владельца

Несколько Claude-служб с одинаковым `cwd=/opt/factory` должны одновременно
проходить периодическую проверку здоровья. Краткое совпадение вызовов
`claude --version` или `claude auth status --json` больше не должно переводить
исправную службу в `unhealthy` и лишать её новых работ.

Защита CARD-0061 сохраняется: общий `runCommand` не ждёт и немедленно возвращает
`ErrCommandAlreadyRunning` для второй идентичной команды. Ожидание ограничивается
только health-probe и его существующим timeout; второй процесс той же команды не
запускается. Настоящая ошибка CLI, пустой/невалидный ответ и истечение timeout
по-прежнему дают `unhealthy`.

## Технический подход и реальные файлы

Сейчас `internal/worker/command.go` строит ключ межпроцессного неблокирующего
`flock` из executable, канонического cwd и argv. Пустой `directory` становится
текущим каталогом процесса. Поэтому одинаковые Claude-службы из `/opt/factory`
получают один ключ. `internal/worker/health.go` вызывает `runCommand` напрямую
для Git, версии runtime, статуса авторизации и GitHub; любая ошибка обязательных
проверок немедленно делает результат нездоровым. Аналогичная, но более широкая
по назначению обёртка `runGitCommand` уже показывает корректную форму ожидания:
повторять только `ErrCommandAlreadyRunning` и прерывать timer по context.

В `internal/worker/health.go` добавляется непубличная health-обёртка над
`runCommand`. Она:

- вызывает `runCommand` с теми же executable, пустым cwd, output limit и argv;
- немедленно возвращает stdout/stderr и любую ошибку, кроме
  `ErrCommandAlreadyRunning`;
- при занятом lock ждёт короткий фиксированный интервал context-aware timer и
  повторяет попытку захватить lock;
- при завершении probe-context возвращает `context.Canceled` или
  `context.DeadlineExceeded`, не делает следующую попытку и не создаёт процесс.

Через эту обёртку проходят все вызовы `runCommand` внутри `checkHealth`: Git,
runtime version, runtime auth и необязательный GitHub probe. Каждый сохраняет
свой отдельный `context.WithTimeout(..., healthCheckTimeout)`, то есть ожидание
lock и выполнение команды делят прежний десятисекундный бюджет. Сам
`runCommand`, ключ lock, `runGitCommand`, интервалы Manager и публичные структуры
не меняются. `readCodexWeeklyLimit` остаётся вне scope: он использует отдельный
долгоживущий stdio-процесс и не вызывает `runCommand`.

В новом `internal/worker/health_test.go` fake executable моделирует совпадающие
Claude probes, процессную ошибку и зависание. Барьер гарантирует реальное
перекрытие двух `checkHealth` из одного канонического cwd, а журнал запусков и
exclusive sentinel доказывают, что retry лишь ждёт lock и не стартует второй
экземпляр одинаковой argv-команды.

## Последовательный план

1. Добавить в `health.go` локальную обёртку с коротким context-aware ожиданием
   только после `errors.Is(err, ErrCommandAlreadyRunning)`.
2. Перевести четыре command-probe в `checkHealth` на обёртку, сохранив отдельные
   probe-context, лимиты вывода, сообщения и правила разбора результатов.
3. Добавить конкурентный Claude-тест: синхронно запустить два health-check из
   одного cwd, удержать первый fake probe, затем отпустить и потребовать два
   результата `healthy` без одновременного второго процесса.
4. Добавить регрессии настоящего non-zero exit и занятого/зависшего probe до
   короткого parent deadline; оба результата должны остаться `unhealthy`, а
   timeout — завершиться в ограниченное время.
5. Оставить существующие тесты CARD-0061 на немедленный возврат общего
   `runCommand`; выполнить целевую команду и `git diff --check`.

## Критерии приёмки

1. Два одновременных `checkHealth` для Claude с одинаковыми executable, cwd и
   argv завершаются `healthy`; оба получают версию и валидный `loggedIn=true`.
2. Во время занятого probe существует не более одного процесса данной точной
   команды. Повторный health-check начинает процесс только после освобождения
   `flock`, а число фактических запусков не включает попытки захвата lock.
3. `runCommand` при идентичном конкурентном вызове всё так же немедленно
   возвращает распознаваемый `ErrCommandAlreadyRunning`; ожидание не появляется
   у supervisor, task, cleanup или иных вызывающих сторон.
4. Ожидание занявшего lock процесса и последующее выполнение укладываются в один
   timeout конкретного health-probe. После cancel/deadline нет нового запуска и
   `checkHealth` завершается `unhealthy` без зависания goroutine или процесса.
5. Non-zero exit, отсутствующая команда, пустая версия, невалидный JSON и
   `loggedIn=false` не повторяются как lock contention и сохраняют прежние
   `unhealthy`-результаты и пользовательские сообщения.
6. Необязательная ошибка GitHub probe по-прежнему только исключает GitHub из
   `SourceAccess`; успешный повтор занятого GitHub probe может добавить доступ.

## Тест-план

- `TestConcurrentClaudeHealthChecksWaitForIdenticalProbe`: fake Git/Claude/GH,
  два параллельных `checkHealth`, общий реальный cwd, barrier на Claude-команде,
  два `healthy`; sentinel запрещает перекрытие одинаковой argv, журнал содержит
  ровно ожидаемые реальные запуски.
- `TestClaudeHealthCheckPreservesCommandFailure`: fake Claude возвращает non-zero
  для обязательного probe; результат `unhealthy`, процесс вызывается один раз,
  ошибка не превращается в retry до timeout.
- `TestClaudeHealthCheckLockWaitHonorsTimeout`: первый вызов удерживает точную
  Claude-команду, второй получает короткий parent deadline; второй завершается
  `unhealthy` с ограниченной длительностью и не создаёт второй процесс, после
  освобождения первый корректно завершается.
- Существующий `TestRunCommandSkipsConcurrentDuplicate` остаётся доказательством
  немедленной семантики CARD-0061; существующие Claude/GitHub integration-тесты
  проверяют совместимость parsing и source access.
- На Implement выполнить обязательную целевую команду ниже. На Verify один раз
  выполнить `go test ./... -count=1`.

## Риски и решения

- Слишком широкий retry скроет дублирование продуктовых команд. Обёртка живёт
  только в `health.go`; `runCommand` и остальные call site не меняются.
- Неограниченное ожидание зависшего CLI заморозит health-loop. Lock wait и сам
  процесс используют один уже существующий probe-context; timer слушает
  `ctx.Done()` и не продлевает deadline.
- Tight loop создаст CPU-нагрузку на нескольких службах. Между попытками есть
  короткий фиксированный timer; отдельный backoff не нужен при десятисекундном
  бюджете и коротких version/status probes.
- Flaky concurrent test может не создать коллизию. Fake probe публикует ready и
  удерживается явным barrier до старта второго check; assertions опираются на
  sentinel/журнал процессов, а не только на wall-clock.
- Повтор после настоящей ошибки может скрыть проблему. Условие retry строго
  `errors.Is(ErrCommandAlreadyRunning)`; exit error, parsing error и пустой вывод
  идут по прежнему пути без повторов.

## Карточка работы

`knowledge/cards/CARD-0098-concurrent-claude-health-probes.md`

## Проверяемая граница готовности

Ниже исчерпывающе перечислены оба файла продуктовой реализации и одна
обязательная целевая проверка. Другие исходники для выполнения спецификации
менять не требуется.

ГОТОВО-КОГДА: файл internal/worker/health.go
ГОТОВО-КОГДА: файл internal/worker/health_test.go
ГОТОВО-КОГДА: команда go test ./internal/worker -count=1 -run '^(TestConcurrentClaudeHealthChecksWaitForIdenticalProbe|TestClaudeHealthCheckPreservesCommandFailure|TestClaudeHealthCheckLockWaitHonorsTimeout|TestRunCommandSkipsConcurrentDuplicate)$'

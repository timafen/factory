# Кириллица сохраняется в задачах и коммитах воркера

## Цель и влияние на пользователя

Владелец и исполнители должны видеть русские названия задач и русские сообщения
коммитов без замены символов на `?`. Это возвращает читаемую историю GitHub и
сохраняет смысл задания, когда процесс воркера стартует из окружения с ASCII
locale.

## Технический подход

Изменить только границу запуска runtime в
`internal/worker/supervisor.go`. Сейчас `superviseRuntime` создаёт
`exec.Command(init.RuntimeExecutable, arguments...)`, задаёт рабочий каталог и
потоки, но не задаёт `Cmd.Env`; поэтому Codex или Claude Code наследуют locale
сервиса-воркера. Добавить небольшой общий конструктор environment, который
сохраняет остальные переменные и явно задаёт UTF-8 locale для дочернего runtime
(в том числе переопределяя конфликтующие `LANG`/`LC_ALL`). Он применяется
одинаково к Codex и Claude Code.

Не изменять prompt, протокол supervisor, хранение задач, HTTP API, базу или
web-интерфейс: строки уже передаются как Go UTF-8 strings. Не добавлять
настройку в worker TOML: корректная кодировка — обязательное свойство процесса,
а не выбор владельца.

В `internal/worker/worker_integration_test.go` расширить fake Codex отдельным
режимом и добавить целевой integration test. Тест запускает supervisor при
наследуемой ASCII-locale, передаёт русское название/инструкцию, требует, чтобы
fake runtime увидел UTF-8 locale, создаёт Git-коммит с русским сообщением и
возвращает русскую строку. Проверка читает сохранённый prompt, результат и
subject коммита и сравнивает их побайтно с исходными строками. До реализации
она должна падать на проверке environment.

## План

1. Выделить в `supervisor.go` формирование environment runtime: базовые
   переменные процесса плюс принудительная UTF-8 locale без дублей
   конфликтующих ключей.
2. Назначить этот environment `exec.Cmd` перед `Start` для обоих поддержанных
   runtime, не меняя аргументы, процесс-группу и перенаправление потоков.
3. Дополнить fake Codex режимом, который проверяет locale, сохраняет
   кириллический prompt, делает русскоязычный коммит и пишет кириллический
   результат.
4. Добавить целевой тест supervisor с исходными `LANG`/`LC_ALL` в ASCII,
   проверяющий exact UTF-8 в prompt, результате и Git subject.

## Критерии приёмки

- Codex и Claude Code получают явную UTF-8 locale, даже если у воркера
  установлена ASCII-locale или конфликтующие `LANG`/`LC_ALL`.
- Остальные переменные окружения runtime сохраняются; аргументы CLI, cwd,
  timeout и управление process group не меняются.
- Русский текст, отправленный воркером в Codex, доходит до runtime без `?`.
- Коммит, созданный runtime с русским subject, сохраняет и возвращает исходные
  UTF-8 символы без `?`.
- Целевая регрессия искусственно начинает с ASCII-locale и падает до добавления
  явного UTF-8 environment.

## План тестирования

- Добавить `TestSupervisorPreservesCyrillicWithUTF8RuntimeLocale` в
  `internal/worker/worker_integration_test.go`; он запускает настоящий путь
  `RunSupervisor` через существующий helper и fake Codex.
- Команда Implement и Verify:
  `go test ./internal/worker -run TestSupervisorPreservesCyrillicWithUTF8RuntimeLocale -count=1`.
- На Verify дополнительно выполнить весь пакет
  `go test ./internal/worker`; полный набор проекта остаётся обязанностью
  отдельной стадии Verify.

## Риски и решения

- Значение UTF-8 locale должно быть доступно в поддерживаемом Linux-образе.
  Реализация выбирает переносимый для Debian/Ubuntu `C.UTF-8`; если образ
  воркера поддерживает только другой UTF-8 locale, это требует явного решения
  владельца и обновления образа, а не возврата к наследованию ASCII.
- Принудительная locale может изменить локализованный текст диагностики CLI,
  но это предпочтительнее потери пользовательских символов. Остальная среда
  сохраняется.
- Не расширять работу до перекодирования уже испорченных записей: `?` не несёт
  информации для восстановления. Это отдельная миграция только при наличии
  исходного текста.

## Карточка

`knowledge/cards/CARD-0125-worker-utf8-runtime.md`

ГОТОВО-КОГДА: файл knowledge/cards/CARD-0125-worker-utf8-runtime.md
ГОТОВО-КОГДА: файл knowledge/specs/worker-cyrillic-utf8.md
ГОТОВО-КОГДА: файл internal/worker/supervisor.go
ГОТОВО-КОГДА: файл internal/worker/worker_integration_test.go
ГОТОВО-КОГДА: команда go test ./internal/worker -run TestSupervisorPreservesCyrillicWithUTF8RuntimeLocale -count=1

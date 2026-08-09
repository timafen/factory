# Спецификация: граница переиспользования Bernstein в Factory

## Решение

Factory не переносит исходный код Bernstein и не заменяет им control plane.
Следующий допустимый шаг — изолированный PoC внешнего исполнителя: один
`Job/Attempt` Factory запускает закреплённую версию `bernstein` как дочерний
процесс, а Bernstein исполняет внутренний DAG в выделенном каталоге попытки.
Интеграция выключена по умолчанию и не меняет существующие задачи Codex и
Claude Code.

Основание сравнения: Factory `origin/main` на `4b9c5d2`; Bernstein 3.13.0,
исходный commit тега `v3.13.0` — `f683ce8dbc6b89d3f91e578cd641d5882bf489dd`,
лицензия Apache-2.0. Репозиторий
`chernistry/bernstein` перенаправляет на `sipyourdrink-ltd/bernstein`; commit
фиксирует исследованный снимок независимо от переименования владельца.

Первичные источники: [репозиторий и README](https://github.com/sipyourdrink-ltd/bernstein/tree/f683ce8dbc6b89d3f91e578cd641d5882bf489dd),
[архитектура](https://github.com/sipyourdrink-ltd/bernstein/blob/f683ce8dbc6b89d3f91e578cd641d5882bf489dd/docs/architecture/ARCHITECTURE.md),
[plans](https://github.com/sipyourdrink-ltd/bernstein/blob/f683ce8dbc6b89d3f91e578cd641d5882bf489dd/docs/architecture/plans.md),
[workflow manifests](https://github.com/sipyourdrink-ltd/bernstein/blob/f683ce8dbc6b89d3f91e578cd641d5882bf489dd/docs/operations/workflow-manifests.md) и
[quality pipeline](https://github.com/sipyourdrink-ltd/bernstein/blob/f683ce8dbc6b89d3f91e578cd641d5882bf489dd/docs/architecture/quality-pipeline.md).

## Что уже есть в Factory

Текущая модель хранит в SQLite версионированный `Workflow`, типизированный
`Automation`, дедуплицированный `Occurrence`, `Task`, `Execution` и `Attempt`.
Control plane принимает ручные, GitHub- и календарные события, выбирает
зарегистрированный worker, выдаёт lease и восстанавливает незавершённую работу.
Worker владеет материализацией репозитория, одной runtime CLI и жизненным циклом
удерживаемого worktree. Браузер показывает общую очередь и состояние.

Целевая архитектура упрощает эти понятия до `Definition → Run → Job → Attempt`,
но сохраняет за Factory входные события, снимок полномочий, durable scheduling,
fleet routing и provider actions. Это продуктовые границы, а не детали запуска
CLI.

## Что Bernstein уже реализует

В исследованном снимке есть:

- декларативные plan YAML: stages, зависимости, параллельные steps, ограничения,
  бюджеты, выбор CLI/model/effort и completion signals;
- workflow manifests с DAG из agent/command nodes, topological execution,
  ограниченными циклами, timeout и dry-run/validate;
- детерминированный tick scheduler без LLM в coordination loop;
- короткоживущие агенты и отдельный git worktree на задачу;
- Codex, Claude Code и множество других CLI adapters;
- janitor, обязательные/необязательные lint/type/test/security gates, очередь
  слияния, retry/escalation и проверка результата по наблюдаемым сигналам;
- локальные журналы lineage/replay и опциональная HMAC audit chain.

Это покрывает значительную часть самописного кода, который иначе понадобился бы
внутри исполнения многошагового Job: разбор DAG, готовность зависимостей,
параллельный spawn, внутренние worktree, сбор проверок и итоговый манифест.

## Матрица владения

| Возможность | Решение | Почему |
| --- | --- | --- |
| DAG, зависимости и параллельные шаги внутри одного Job | PoC на Bernstein | Готовый валидатор и детерминированный scheduler |
| CLI adapters и запуск короткоживущих агентов | PoC на Bernstein | Не размножать wrappers runtime |
| Внутренние worktree и merge/quality gates | PoC на Bernstein | Использовать как единый комплект, не копировать части |
| Completion signals, lineage и локальные receipts | PoC на Bernstein | Проецировать как evidence Attempt, сохраняя оригинальные артефакты |
| Definition, Trigger, Run, Job, Attempt и fleet routing | Оставить Factory | Это внешний продуктовый и durable coordination слой |
| Webhook admission, GitHub identity и provider actions | Оставить Factory | Bernstein не должен получать полномочия control plane |
| Канонический статус, retry Job и идемпотентность | Оставить Factory | Два источника истины недопустимы |
| UI/API владельца, история и лимиты организации | Оставить Factory | Локальный Bernstein UI/API не заменяет общий интерфейс |
| File-based `.sdd` как долговременная БД | Не принимать | Factory уже использует SQLite; `.sdd` — артефакт одной попытки |
| Копирование Python-модулей в Go control plane | Не принимать | Создаёт fork и связывает релизные циклы без пользы процесса |

## Контракт PoC

1. Новый runtime capability называется `bernstein`; зарегистрировать его может
   только Runner, где установлен поддерживаемый бинарник точной версии. Обычный
   Job никогда не маршрутизируется туда без явного требования Definition.
2. Factory передаёт runner неизменяемый снимок Job и ограниченный plan-файл.
   Аргументы процесса формируются массивом без shell. Произвольный `command` node
   в первой версии запрещён; разрешены только agent steps и заранее названные
   проектные проверки.
3. Runner создаёт отдельный корень попытки. Bernstein получает свой checkout и
   сам владеет вложенными task worktree; существующий Factory worktree не
   передаётся ему как одновременно управляемый git root.
4. Factory остаётся единственным владельцем lease, deadline, отмены и
   терминального состояния Attempt. Отмена сначала посылает штатное завершение,
   затем после grace period завершает process group. Повторная выдача создаёт
   новую попытку, а не продолжает скрыто работающий процесс.
5. События Bernstein преобразуются в ограниченный поток progress/evidence.
   Полный `.sdd` bundle, plan, версия бинарника, commit результата, gate outcomes
   и lineage receipt сохраняются как артефакты попытки. Текст из артефактов не
   становится управляющей командой Factory.
6. Credentials выдаются только на чтение исходника и на разрешённые model APIs.
   GitHub/provider write credentials и ключи control plane дочерний процесс не
   получает. Публикация остаётся типизированным Provider Action Factory.
7. Успех Bernstein — необходимое evidence, но не право менять статус Run или
   публиковать код. Runner проверяет exit code, структуру результата, принадлежность
   commit разрешённому репозиторию и обязательные gates, затем сообщает Attempt.
8. Версия закреплена в образе Runner и SBOM. Обновление проходит тот же contract
   suite. В поставке сохраняются Apache-2.0 LICENSE/NOTICE и attribution; точный
   состав уведомлений проверяется до распространения образа.

## Проверка PoC и критерии приёмки

PoC не считается внедрением, пока не выполнены все критерии:

1. **Эквивалентность DAG.** Фикстуры `linear`, `fan-out/fan-in`, failed upstream
   и retry дают ожидаемый порядок и ровно один терминальный результат каждого
   step при трёх повторных запусках.
2. **Изоляция git.** Два параллельных step меняют непересекающиеся файлы; исходный
   checkout Factory остаётся чистым, итоговый commit содержит оба изменения, а
   попытка конфликта или выхода пути за корень завершается безопасным отказом.
3. **Ворота.** Намеренно сломанные lint, test и completion signal не дают Factory
   принять Attempt; успешная фикстура прикладывает результаты каждого обязательного
   gate и проверяемый lineage receipt.
4. **Жизненный цикл.** Timeout, отмена, падение процесса и потеря runner lease не
   оставляют дочерних процессов; повторная попытка не дублирует публикацию и
   имеет отдельный каталог и audit bundle.
5. **Безопасность границы.** Пробелы, кавычки и shell metacharacters в goal не
   исполняются; `command` node и неизвестный schema field отвергаются до запуска;
   дочернее окружение не содержит provider write credentials.
6. **Совместимость.** При выключенном feature flag существующие runtime и API
   дают байт-в-байт прежние запросы/ответы. При отсутствии или несовпадении
   версии Bernstein runner объявляет capability недоступной с понятной причиной.
7. **Наблюдаемость.** UI/API Factory показывает словесные названия step, текущий
   progress, итог gates и ссылку на артефакт; внутренние ID не являются единственным
   объяснением состояния.
8. **Лицензия и эксплуатация.** Сборка образа содержит закреплённую версию, hash,
   SBOM, LICENSE и NOTICE; offline contract test выполняется без сети после
   установки зависимостей.

Минимальный автоматический набор: Go contract tests с фальшивым executable для
argv/env/cancel/result projection; интеграционная фикстура с настоящим закреплённым
Bernstein для DAG/worktree/gates; существующие worker/control-plane тесты при
выключенном флаге; `go test ./...`, web unit/type/build и `git diff --check` перед
слиянием.

## Условия решения после PoC

Продолжать интеграцию можно только если PoC сокращает код исполнения DAG и
worktree/gates, не создавая второй durable scheduler, и все восемь критериев
проходят детерминированно. Отказаться от интеграции следует, если для неё нужно
передать Bernstein provider write credentials, синхронизировать `.sdd` с SQLite
как две равноправные БД, обходить его worktree/quality pipeline или поддерживать
существенный fork. В этом случае спецификация остаётся источником идей для
собственной модели, но не разрешением копировать реализацию.

## Вне области

- изменение Go, Python, UI, миграций, worker image или runtime в этой поставке;
- установка зависимости и запуск Bernstein на production/staging;
- замена текущего одиночного выполнения Codex/Claude Code;
- импорт Bernstein triggers, web UI, task server, cloud/cluster или его planner;
- автоматическая публикация веток/PR и любые новые provider permissions;
- юридическое заключение о лицензии.

## Следующее действие

Отдельной карточкой реализовать только offline PoC адаптера на disposable
runner: одна fan-out/fan-in фикстура, один безопасный отказ gate и полный захват
артефактов. До результатов PoC продуктовую схему и UI не менять.

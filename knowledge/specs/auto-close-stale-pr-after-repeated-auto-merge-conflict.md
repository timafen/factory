# Автоматическое закрытие устаревшего PR после повторного AUTO-MERGE-конфликта

## Цель и влияние на владельца

Если AUTO-MERGE второй раз получает content conflict, а та же работа уже
влита другим PR в ту же целевую ветку, Pilot должен закрыть оставшийся
устаревшим PR и не создавать ещё один круг исправления. Владелец видит, что
работа действительно доставлена, а не получает лишнюю задачу и открытый
«призрачный» PR.

Безопасная граница — точное совпадение неизменяемого `work_id` в машинном
маркере, который Pilot записал в описание обоих PR. Заголовок, имя ветки,
похожий текст, отсутствие маркера и обычный человеческий PR не доказывают,
что работа одна, и не дают права на закрытие.

## Технический подход и реальные файлы

Фактический путь уже существует в `pilot/pilot.py`: успешный Verify создаёт
`merge_intent`, `recover_merge_intents()` переводит первый конфликт в фазу
`conflict`, а `resume_merge_conflicts()` создаёт один возврат в
`Implement + Test`. В этой точке нужно добавить безопасную сверку второго
конфликта, не меняя UI, control-plane API или worker.

1. При создании Pilot PR расширить тело, формируемое `gh_merge()`, ровно одним
   маркером `<!-- factory-work-id:<work_id> -->`. Значение берётся из
   `detail.task.work_id`, сохраняется снимком в `merge_intent` и не извлекается
   из заголовка или отчёта агента. Повторная попытка публикации использует тот
   же маркер; `pilot/config.example.json` не менять, потому что он не содержит
   тела PR или workflow-инструкции его формирования.
2. Передать в intent целевую ветку отдельно от владелецкого названия работы
   (`base`): например, как `base_branch`, полученную из метаданных текущего PR
   или default branch. Сохранить `conflict_count`: первый conflict даёт 1,
   correction-переход переносит счётчик к следующему Verify, второй — 2.
   Legacy intent без `work_id` или счётчика остаётся совместимым, но не может
   автоматически закрыть PR.
3. При `conflict_count >= 2` получить у GitHub текущий PR этой ветки и
   открытый статус, а также bounded список PR репозитория. Текущий PR обязан
   быть единственным открытым PR с точной head-веткой и целевой base-веткой.
   Кандидат-доказательство обязан быть другим PR с `merged_at`, той же exact
   base-веткой и ровно одним валидным маркером, равным snapshot `work_id`.
   Тело текущего PR проверяется тем же parser; неполный или неоднозначный
   ответ GitHub блокирует закрытие.
4. Закрывать только текущий открытый PR через явный `gh pr close`/GitHub API
   с фиксированным audit-комментарием, содержащим ссылку или номер
   подтверждающего merged PR. Перед мутацией сохранить intent в
   `superseding` с номерами/URL, причиной и временем; после подтверждённого
   close записать `superseded`, `superseded_by`, `closed_at` и audit reason.
   После `superseded` не вызывать `gh_merge`, `create_child_task`, delivery или
   `mark_final`: это только завершение stale PR, а доказательство доставки —
   уже merged PR.
5. При timeout или неясном результате close перечитать PR: закрытый PR можно
   один раз довести до `superseded`, открытый остаётся в `superseding` для
   безопасного повторения. Повторный Pilot не комментирует и не закрывает
   второй раз. Нет marker, нет merged-кандидата, другая base, human PR,
   несколько неоднозначных текущих PR или любая ошибка GitHub — fail closed и
   сохраняет обычный correction flow.

Реальные файлы реализации:

- `pilot/pilot.py` — marker formatter/parser, immutable intent fields,
  bounded GitHub lookup, idempotent close и ветвление conflict recovery;
- `pilot/test_pilot.py` — изолированные регрессии класса
  `MergeConflictRecoveryTests`.

`pilot/config.example.json` проверен как источник настроек: специальных
инструкций создания PR в нём нет, поэтому он вне diff.

## Последовательный план

1. Зафиксировать формат маркера и строгий parser с требованием ровно одного
   значения; добавить `work_id`, `base_branch` и conflict generation в intent
   и перенести их через correction → Review → Verify.
2. Изменить `gh_merge()` так, чтобы Pilot создавал только собственное тело PR
   с marker и не подставлял пользовательский текст как идентификатор.
3. Реализовать read-only lookup текущего PR и merged PR с точной проверкой
   repository, head, base, state, `merged_at`, marker и исключением того же
   PR из доказательства.
4. Добавить durable-переходы `superseding` → `superseded`, re-read после
   неоднозначного close и запрет повторного correction для superseded intent.
5. Добавить позитивные и fail-closed тесты, затем запустить целевую проверку
   `MergeConflictRecoveryTests`; полный набор оставить этапу Verify.

## Критерии приёмки

- Каждый новый Pilot PR получает ровно один marker с exact `work_id`; старый
  intent без снимка не получает guessed identity.
- Первый merge conflict сохраняет существующий возврат в Implement и не
  закрывает PR; второй конфликт увеличивает generation и запускает сверку.
- Открытый PR закрывается только при exact marker match у текущего и другого
  уже merged PR, совпадающей repository/base и явном `merged_at`.
- Успешное закрытие один раз переводит intent в `superseded`, сохраняет
  подтверждающий PR и причину; correction task, повторный merge, delivery и
  ложный owner-done не создаются.
- Отсутствующий/двойной/искажённый marker, совпадение только title, human PR,
  другая base, отсутствие merged PR и любая ошибка GitHub никогда не закрывают
  PR и оставляют обычный repair flow.
- Restart после `superseding` или `superseded` не повторяет close/comment и не
  создаёт дубликат task.
- В diff продуктовой поставки нет UI, control-plane, worker и config-файлов;
  реализация ограничена `pilot/pilot.py` и `pilot/test_pilot.py`.

## Тест-план

Расширить `MergeConflictRecoveryTests` с mock GitHub и временным `STATE_PATH`:

- второй conflict + открытый Pilot PR + другой merged PR с тем же marker и
  base: ровно один close, `superseded`, audit evidence и ноль correction tasks;
- повторный вызов и restart: нет второго close/comment, а уже закрытый PR
  доводится до terminal intent;
- первый conflict: сохраняется текущий correction flow;
- разные `work_id`, одинаковые title, отсутствующий/двойной/искажённый marker,
  human PR и другая base: close не вызывается, создаётся обычный repair task;
- list/get/close error, timeout и неоднозначный PR: fail closed, intent не
  объявляется доставленным;
- новый marker берётся из exact `task.work_id`, а не из legacy title или
  случайного текста отчёта.

Обязательная проверка для реализации:
`python3 -m unittest -q pilot.test_pilot.MergeConflictRecoveryTests`

На текущем этапе Specification выполнен существующий целевой класс; новые
регрессии добавляются на этапе Implement + Test.

## Риски и решения

- Ложное закрытие независимого PR: требовать exact machine marker, другой PR,
  merged status и exact base; title и ветка остаются только диагностикой.
- Человек скопировал marker: объектом мутации всегда остаётся только текущий
  Pilot PR, а неподтверждённый или неоднозначный merged PR не используется.
- GitHub race или сетевой сбой: durable `superseding` плюс повторное чтение
  состояния; при сомнении ничего не закрывать и не считать работу доставленной.
- Старые PR и intents: отсутствие immutable `work_id` означает безопасный
  отказ от auto-close и сохранение существующего repair flow.
- Удалённая ветка или несколько PR: bounded lookup и fail-closed вместо
  выбора «похожего» PR; отдельная ручная уборка остаётся возможной.
- Повторное создание PR: единый marker formatter и сохранение snapshot
  `work_id` исключают расхождение между correction и Verify.

## Карточка работы

`knowledge/cards/CARD-0165-auto-close-stale-pr-after-repeated-auto-merge-conflict.md`
— отдельная карточка текущей работы. Номер и точный путь проверены по свежему
`origin/main` и 1154 опубликованным refs: номера/пути до CARD-0164 заняты,
CARD-0165 и этот путь свободны.

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: команда python3 -m unittest -q pilot.test_pilot.MergeConflictRecoveryTests

# Автоматическое закрытие устаревшего PR после AUTO-MERGE-конфликта

## Цель и влияние на владельца

Если AUTO-MERGE второй раз получает content conflict, а та же самая работа уже
влита другим PR в ту же целевую ветку, Pilot закрывает оставшийся открытым PR и
не создаёт лишнюю задачу исправления. Владелец не тратит время на уже
доставленную работу и видит в журнале причину закрытия и PR, подтвердивший
вливание.

Безопасная граница: «та же работа» означает только точное совпадение
неизменяемого `work_id` в машинном маркере, который Pilot записал в описание
обоих PR. Совпадение заголовка, ветки, текста, отсутствие маркера и любой
человеческий PR не являются основанием закрытия.

## Технический подход и реальные файлы

`pilot/pilot.py` уже сохраняет `merge_intent`, переводит его в `conflict` в
`recover_merge_intents()` и в `resume_merge_conflicts()` создаёт возврат в
`Implement + Test`. Изменить этот путь следующим образом.

1. При подготовке Pilot PR добавить в его body строго один машиночитаемый
   маркер, например `<!-- factory-work-id:<work_id> -->`; значение берётся из
   durable `task.work_id`, не из title. Повторная публикация/обновление PR
   сохраняет тот же маркер, а `work_id` сохраняется в intent как snapshot.
2. После повторного AUTO-MERGE-conflict, до перехода `conflict` в `repairing`,
   запросить GitHub PR текущей ветки и список merged PR для `intent.repository`
   и `intent.base`. Выбрать кандидат только если: текущий PR открыт, оба body
   содержат валидный точный marker, marker равен snapshot `work_id`, другой PR
   имеет `merged_at`, а его base точно равен целевой ветке intent.
3. При единственном или нескольких подходящих merged кандидатах закрыть
   **только текущий открытый Pilot PR** через GitHub API с явным комментарием,
   записать в intent terminal phase `superseded`, номер/URL merged PR,
   timestamp и audit reason. Не вызывать `create_child_task`, `gh_merge`,
   delivery или owner-done: работа уже представлена другим merged PR и этот
   шаг лишь прекращает устаревший PR.
4. Ошибка GitHub, нет текущего PR, нет маркера, неодинаковые `work_id`, другая
   base или отсутствие merged кандидата — fail closed: PR не закрывается и
   остаётся существующий сценарий correction task. Повтор цикла не должен
   повторно закрывать/комментировать PR после durable `superseded`.

Реализация и проверки ограничены:

- `pilot/pilot.py` — marker, GitHub lookup/close helper, durable intent audit и
  ветвление recovery до создания repair task.
- `pilot/test_pilot.py` — изолированные regression tests
  `MergeConflictRecoveryTests` с mocked GitHub.

`pilot/config.example.json` не меняется: PR создаётся непосредственно в
`gh_merge()` с фиксированным body, а не из workflow prompt конфигурации.

## Последовательный план

1. Найти существующий путь публикации/обновления Pilot PR и сделать единый
   formatter/parser строгого marker без title fallback.
2. Дополнить `merge_intent` immutable `work_id` и данными открытого PR,
   совместимо обработав legacy intents без этих полей как «не закрывать».
3. В conflict recovery получить и проверить текущий и merged PR, включая
   identity репозитория и exact base branch.
4. Сначала durably записать решение/идентификатор кандидата либо обеспечить
   идемпотентное close по PR number; затем закрыть открытый PR, сохранить
   `superseded` и исключить возврат в Implement.
5. Добавить tests на positive flow, повторный цикл, разные work_id, marker
   отсутствует/искажён, human PR, одинаковый title и другую target branch.

## Критерии приёмки

- Каждый PR, созданный Pilot для pipeline work, содержит ровно один неизменный
  marker с его `work_id`.
- После повторного merge-conflict открытый PR закрывается лишь при exact
  marker match с уже merged другим PR той же base branch.
- Для успешного close intent становится `superseded`, содержит audit evidence,
  и correction task не появляется.
- PR без marker, human PR и совпадение только title никогда автоматически не
  закрываются; они продолжают текущий repair flow.
- Ошибка/неполный ответ GitHub не меняет PR и не объявляет работу завершённой.
- Перезапуск Pilot не создаёт второго close/comment/task для уже обработанного
  intent.

## Тест-план

Расширить `MergeConflictRecoveryTests` mock-ответами GitHub и проверить:

- повторный conflict + open Pilot PR + merged PR с тем же marker и base:
  один close, `superseded`, нет `create_child_task`;
- второй cycle/restart не повторяет API mutation;
- разные `work_id`, одинаковые titles, отсутствующий/двойной/искажённый marker,
  human PR и другая base: close не вызывается, создаётся обычный repair task;
- GitHub list/get/close error: fail closed и PR не меняется;
- marker создаётся с exact `task.work_id` и не берётся из legacy title.

Основной новый сценарий назвать
`test_second_conflict_closes_stale_pr_when_matching_work_was_merged`, чтобы
обязательная команда проверяла именно суть задачи, а не весь существующий
класс косвенно.

## Риски и решения

- Ложное закрытие независимого PR: только exact machine marker + merged status
  + exact base; title heuristic запрещена.
- Поддельный marker в human PR: закрывается только текущий открытый PR,
  связанный с Pilot intent; чужой PR никогда не является объектом close.
- GitHub race/сетевая ошибка: повторно прочитать состояние при retry и
  fail-closed, не считать закрытие доставкой работы.
- Legacy intents/PR: нет immutable `work_id` или marker — совместимо вернуть
  в Implement, не мигрировать предположением.

## Карточка работы

`knowledge/cards/CARD-0127-auto-close-stale-duplicate-pr.md` — отдельная
карточка; путь проверен в свежем `origin/main` и опубликованных ветках.

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: команда python3 -m unittest -q pilot.test_pilot.MergeConflictRecoveryTests.test_second_conflict_closes_stale_pr_when_matching_work_was_merged

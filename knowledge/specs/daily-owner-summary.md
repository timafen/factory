# Спецификация: ежедневная сводка владельцу о влитом, выпущенном и результате

## Цель и влияние на владельца

Каждый день владелец получает в канал `https://ntfy.sh/timafen-a8523d037f21`
одну утреннюю сводку в 08:00 по `America/Chicago`. Сводка отвечает простым
языком на три вопроса: что действительно влито в `main`, что действительно
выпущено и принято health-проверкой, и что это дало (изменение наблюдаемых
метрик/результатов, а также честно обозначенные тупики). Время считается в
именованной IANA-зоне с переходами на летнее время; за одну местную дату
отправляется не более одной сводки.

Сводка не объявляет Verify PASS или merge выпуском: источником истины остаются
merge receipts, accepted delivery receipts и реальные owner decisions. При
неполных данных она показывает «не подтверждено», а не додумывает эффект.

## Технический подход и реальные файлы

Использовать существующий Pilot durable state и журналы: merge/delivery
receipts, `recent_done_block`, метрики тупиков и outbox уведомлений. Добавить
отдельное состояние ежедневного отчёта с `local_date`, вычисленной в
`zoneinfo.ZoneInfo("America/Chicago")`, временем отправки, snapshot входных
receipt/metrics и idempotency key `daily-owner-summary:<local_date>`. Сначала
атомарно резервировать ключ, затем строить и отправлять сообщение; повторный
запуск того же местного дня не делает второй push. Сбой push оставляет запись
для bounded retry без создания второй сводки.

Планировщик должен запускать задачу по cron `0 8 * * *` и передавать timezone
`America/Chicago`, используя уже существующую проверку IANA-зон и scheduler
occurrences. Нельзя вычислять время через UTC-offset или локальную timezone
машины. В payload должны быть: период/местная дата, списки merged и released
работ с человекочитаемыми названиями, эффект только из подтверждённых
метрик/решений, blocked/unknown и ссылка на канал.

Реальные файлы реализации: `pilot/pilot.py`, `pilot/test_pilot.py`,
`pilot/config.example.json`, `internal/controlplane/schedule_cron.go`,
`internal/controlplane/schedule_automations_test.go`, при необходимости
`internal/controlplane/schedule_runtime.go` и `internal/protocol/types.go`.
Публичный UI и схема SQLite не меняются; если для повторяемого snapshot
потребуется новый durable-файл Pilot, его путь и формат должны быть описаны в
тесте миграции/перезапуска.

## Последовательный план

1. Описать входной snapshot и formatter сводки, отделив подтверждённые merge,
   accepted release, effects, blocked и unknown.
2. Добавить расписание 08:00 с IANA timezone и durable local-date idempotency;
   проверить DST-переходы и повторный запуск occurrence.
3. Связать snapshot с существующим outbox/ntfy dispatcher: reservation до
   внешней отправки, retry после ошибки, один logical event на дату.
4. Добавить recovery после crash до/после reservation, записи outbox и push;
   исключить отправку будущей или второй даты.
5. Обновить пример конфигурации и операторское описание, затем выполнить
   целевые Python/Go тесты и `git diff --check`.

## Критерии приёмки

- Владелец получает сводку в 08:00 `America/Chicago`, включая корректные
  даты до и после DST; UTC-offset машины не влияет на расписание.
- Для одной местной календарной даты существует максимум один logical
  summary event и максимум одна успешная отправка после идемпотентного retry.
- Влитым считается только подтверждённый merge receipt; выпущенным — только
  accepted delivery receipt с live acceptance. Verify PASS сам по себе не
  попадает в released.
- «Что это дало» строится из сохранённых метрик/решений за определённый
  период и различает нулевой эффект, отсутствие данных и блокировку.
- Crash/restart на каждой границе не теряет отчёт и не удваивает push; ошибка
  ntfy не помечает отчёт отправленным.
- Существующие scheduler и outbox тесты не регрессируют; UI, чужие карточки и
  продуктовые исходники вне перечисленных файлов не изменяются.

## Тест-план

Добавить целевой `pilot/test_pilot.py` сценарий: два запуска в один день,
ошибка push, restart и успешный retry дают одну запись с одним ключом и одну
сводку. Зафиксировать snapshots с merged-only, released, blocked и unknown.
Добавить проверки `0 8 * * *` + `America/Chicago` на январскую дату, летний
переход и зимний переход, а также rejection fixed-offset/невалидной зоны.
Проверить scheduler occurrence dedup и outbox recovery существующими
`internal/controlplane/schedule_automations_test.go`/Go-тестом, если граница
реализуется в control plane. Обязательная команда этапа реализации:
`python3 -m unittest pilot.test_pilot.DailyOwnerSummaryTests`.

## Риски и решения

- DST может дать неверный день при ручном offset: использовать только
  `ZoneInfo` и тесты переходов.
- Повтор ntfy может появиться после неопределённого сетевого ответа: durable
  idempotency key и локальная дедупликация; at-least-once transport честно
  отражается в журнале.
- «Эффект» может быть недоказуем: показывать unknown/нулевой эффект с
  источником, не генерировать причинность из текста агента.
- Устаревший receipt может попасть в отчёт: snapshot ограничить местной
  датой/окном и хранить время источника в payload.

## Карточка работы

`knowledge/cards/CARD-0097-daily-owner-summary.md` — отдельная карточка этой
работы; предыдущая triage-ветка недоступна в origin, поэтому выводы сверены с
свежим `origin/main` и фактическим кодом. Implementation commit будет добавлен
на этапе Implement до финального документационного коммита карточки.

Реализационные файлы:

`pilot/pilot.py`

`pilot/test_pilot.py`

`pilot/config.example.json`

`internal/controlplane/schedule_cron.go`

`internal/controlplane/schedule_runtime.go`

`internal/controlplane/schedule_automations_test.go`

`internal/protocol/types.go`

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: команда python3 -m unittest pilot.test_pilot.DailyOwnerSummaryTests

# Аудит переноса сторожа и автоматизаций Fable в Factory

## Решение

Текущая матрица считается окончательным объёмом этой проверки. Все известные и
доступные для проверки механизмы присутствуют в Factory и подтверждены целевыми
автоматическими тестами. Абсолютное совпадение с исторической Fable не заявляется:
её исходный репозиторий или снимок недоступен, поэтому историческая полнота
недоказуема. Если источник Fable появится, нужен отдельный дополнительный аудит.

## Проверяемая матрица

| Возможность | Реализация Factory | Автоматическое доказательство | Остаточный пробел |
| --- | --- | --- | --- |
| Автономный сторож потерянных переходов конвейера | `pipeline_watch` в `pilot/pilot.py`, устойчивое локальное состояние и вызов из цикла pilot | `PipelineWatchTests`: ожидание, одиночное продолжение, подавление дубля, пауза владельца, финальная стадия, фильтр заголовка и однократная эскалация | Нет сравнения с неизвестными эвристиками Fable |
| GitHub issue запускает workflow | типизированный `github_issue`, долговечные occurrences и идемпотентный request key в control plane | `TestAutomation*` и `TestHTTPAutomation*`: жизненный цикл, dispatch, replay, disable, preview и HTTP | Неизвестны дополнительные фильтры старой системы |
| GitHub pull request запускает workflow | типизированный `github_pull_request`, фильтры draft/label/base и отдельные occurrences | `TestPullRequestAutomation*` и `TestHTTPPullRequestAutomation*`: фильтры, сохранение и дедупликация | Нет исходника Fable для сопоставления каждого фильтра |
| Cron запускает workflow | cron parser, timezone/DST, due/catch-up, run-now и schedule runtime | `TestScheduleAutomation*` и связанные cron-сценарии: preview, dispatch, восстановление, disable и HTTP | Неизвестен полный перечень исторических расписаний Fable |
| Автоматизации переживают рестарт | восстановление зарезервированных проверок и pending occurrences из хранилища | `TestAutomationRestartRecoversReservedCheckAndPendingOccurrence`, PR restart deduplication и schedule recovery/catch-up | Нет исторических данных Fable для миграционной сверки |
| Оператор управляет автоматизациями | HTTP lifecycle, preview/test, enable/disable и run-now | `TestHTTPAutomationLifecycleAndPreview`, строгие PR и schedule HTTP-сценарии | Внешний UX Fable не сравнивался |

## Критерии приёмки

- Матрица явно связывает каждый известный механизм с реализацией Factory и
  автоматическим тестом.
- Целевой класс сторожа проходит без сети и второго процесса.
- Целевые Go-сценарии подтверждают GitHub issue/PR, cron, восстановление и
  операторские API.
- Вывод ограничен доказуемым: подтверждён перенос всех известных и доступных
  механизмов, но не абсолютная историческая полнота Fable.
- Недоступность Fable не блокирует этот аудит; появление исходников создаёт новый
  объём проверки, а не меняет результат текущей.

## Проверка

```text
python3 -m unittest pilot.test_pilot.PipelineWatchTests
go test ./internal/controlplane -run 'Test(Automation|PullRequestAutomation|HTTPAutomation|ScheduleAutomation)' -count=1
```

## Вне объёма

- Восстановление или поиск исходного репозитория Fable.
- Новая реализация сторожа, триггеров, API или интерфейса.
- Утверждение полного паритета с недоступной исторической системой.

## Карточка

`knowledge/cards/CARD-0120-fable-automation-migration-audit.md`

ГОТОВО-КОГДА: файл knowledge/specs/fable-automation-migration-audit.md
ГОТОВО-КОГДА: команда python3 -m unittest pilot.test_pilot.PipelineWatchTests

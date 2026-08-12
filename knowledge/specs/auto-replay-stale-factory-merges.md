# Спецификация: автоматическое восстановление отставшего выпуска Factory

## Цель и влияние на владельца

После потери очереди или перезапуска Pilot сам замечает, что production
Factory отстаёт от актуального `origin/main`, и создаёт один объединённый
автоматический выпуск. Владельцу не нужно вручную повторять release: блокировка
release-lock остаётся сохранённым намерением и повторяется автоматически.

Готовность уже доставленного SHA не создаёт второй выпуск. Если production
уже содержит SHA `origin/main`, либо установленная версия не является предком
актуального main (например, после отката), Pilot ничего не запускает и пишет
диагностику. Ручной выпуск, исправление сторонних сигналов проверок и staging
торгового проекта не входят в работу.

## Технический подход и реальные файлы

Источником истины об установленной Factory станет атомарно опубликованный
`release-info.json`: `ops/fx-factory-release` записывает в него `sha` только
после успешной установки, проверки health/worker и commit journal. В
`ops/fx` добавить стабильный read-only машинный режим `factory release-info`
для выдачи полного SHA (не разбирать локализованный человекочитаемый текст).
Ошибка, пустой или невалидный SHA означает «неизвестно» и fail-closed: новый
автовыпуск не создаётся.

В `pilot/pilot.py` добавить отдельную reconciliation-проверку только для
точного remote identity `github.com/timafen/factory`. Она получает свежий
`origin/main` через существующий фиксированный `git fetch` в checkout Factory,
а затем сравнивает его с установленным SHA через `git merge-base --is-ancestor`:

| Условие | Действие |
| --- | --- |
| SHA совпадают | Ничего не создавать. |
| Установленный SHA — предок актуального `origin/main` | Долговечно зарезервировать/присоединить один recovery generation с актуальным SHA. |
| Установленный SHA не предок, данные недоступны или некорректны | Ничего не выпускать; записать наблюдаемую причину. |

Recovery generation использует существующий `delivery_state_v2.targets.factory`
и тот же immutable `generation.id`/broker operation, а не `merge_intents` и не
псевдо-Verify задачу. У него есть явный тип ожидания `reconciliation`, поэтому
после успеха он отправляет owner-уведомление о восстановленном выпуске, но не
вызывает `mark_final` для несуществующей задачи. Повторная сверка присоединяется
к `reserved` generation; при `launching`/`running` сохраняет только запрос
следующего поколения по уже существующим правилам. Для того же SHA нельзя
создать второй active или terminal generation.

`poll_delivery_state()` сохраняет поведение CARD-0051/CARD-0084: `locked`
оставляет generation `reserved` с `next_retry_at`, а повтор POST имеет тот же
operation id. Перед переводом Factory generation в `completed` Pilot заново
читает установленный SHA и требует его точного совпадения с `commit_sha`;
иначе generation остаётся честно незавершённым/failed без receipt или ложного
done. Откат остаётся отдельным действием: divergent SHA не превращается в
автоматическое переигрывание main.

Изменения ограничиваются `pilot/pilot.py`, `pilot/test_pilot.py`, `ops/fx` и
`ops/test-fx-factory-release.sh`. Broker, release driver, UI, control plane и
адаптер `tarser-operations` не меняются.

## Последовательный план

1. В `ops/fx` определить стабильный read-only контракт полного установленного
   SHA; покрыть отсутствие и повреждение metadata fail-closed проверкой.
2. В Pilot реализовать чтение этого контракта, обновление `origin/main` и
   классификацию equal/ahead/divergent/unknown без shell-инъекций.
3. Добавить durable reconciliation record и создание/присоединение generation
   Factory без `merge_intent` и без ложной Verify-задачи.
4. Связать lock retry с этим record: после `rc=8` сохранить тот же id, повторить
   автоматически и взять актуальный SHA, пока generation ещё `reserved`.
5. Перед terminal completion сверить installed SHA с generation SHA; сохранить
   dedupe-маркер только после подтверждённой доставки.
6. Добавить регрессии пустого состояния, lock/restart, повторного цикла,
   divergent rollback и изоляции tarser; выполнить целевой набор.

## Критерии приёмки

- При пустых `delivery_state_v2.targets` и production позади main Pilot создаёт
  ровно один Factory recovery generation с SHA свежего `origin/main`.
- `locked` сохраняет generation и автоматически повторяет тот же broker
  operation после задержки; restart между этими шагами не теряет намерение.
- Повторный цикл до и после delivery не создаёт второй выпуск уже доставленного
  SHA; успех признаётся только после точного installed-SHA match.
- При rollback/divergent SHA, недоступном `release-info` или невалидных данных
  автозапуск отсутствует и есть диагностическая причина.
- Обычные `merge_intents`, rollback и tarser staging сохраняют действующее
  поведение; reconciliation не вызывает `mark_final` для синтетического wait.

## Тест-план

В `pilot/test_pilot.py` добавить fixture с настоящим state file, фиксированным
fresh `origin/main`, ответом release-info и подменённым broker. Она доказывает:
пустой state + старый installed SHA создаёт один generation с новым SHA;
второй цикл не создаёт второй; `locked` переживает reload state и повторяет тот
же id; terminal broker success при несовпавшем installed SHA не создаёт
receipt/outbox; divergent SHA и ошибка release-info не запускают broker.

Отдельными случаями проверить, что обычный `recover_merge_intents()` продолжает
работать, rollback SHA не вызывает backfill, а `tarser-operations` не читает
Factory release-info и не получает generation. В
`ops/test-fx-factory-release.sh` проверить полный валидный SHA нового read-only
контракта и отсутствие SHA при повреждённом/отсутствующем metadata.

Обязательная проверка: `python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests`.

## Риски и решения

- SHA из имени release или UI может быть неполным/устаревшим. Решение: читать
  только атомарный `release-info.json` через ограниченный `fx` контракт и
  принимать строго полный hex SHA.
- Откат намеренно делает production не-предком main. Решение: divergent путь
  fail-closed; автоматизация не отменяет rollback.
- Broker мог завершиться, а release metadata ещё не соответствует generation.
  Решение: terminal completion требует повторной проверки installed SHA.
- Частые циклы могут создать дубликаты. Решение: единственный durable target,
  current generation и SHA-dedupe; `locked` повторяет тот же id.
- Обобщение на другие репозитории опасно. Решение: reconciliation жёстко
  ограничена Factory; существующие adapters не меняются.

## Карточка работы

`knowledge/cards/CARD-0090-auto-replay-stale-merges.md`

## Готово, когда

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл ops/fx
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: команда python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests

# Спецификация: возобновление — единая машина состояний слияния и выпуска

## Цель и влияние на владельца

После Verify и слияния владелец не должен видеть «Задача выполнена», пока
конкретное поколение выпуска не принято durable release driver и не прошло
живую приёмку. Он видит один из честных результатов: выпуск ожидает запуска,
идёт, завершён или не прошёл. Повтор Pilot либо broker после сбоя не создаёт
второй физический выпуск и не теряет уже слитую работу.

Это возобновление фиксирует проверяемый контракт уже поставленной модели V2;
этап Specification не изменяет продуктовый код. Базовая реализация находится
в `origin/main`, а дальнейшая работа обязана сохранять описанные ниже границы.

## Технический подход и реальные файлы

`pilot/pilot.py` хранит `delivery_state_v2`: для разрешённой пары repository
identity + adapter есть `current_generation`, монотонный номер и поколения с
фазами `reserved`, `launching`, `running`, `completed`, `failed`. До внешнего
`gh_merge` сохраняется `merge_intent`; receipt и delivery wait записываются
после результата merge. Recovery обрабатывает intents до cursor `processed`.
`reserved` принимает новые waits в то же N при lock `rc=8`; merge в
`launching`/`running` ставит единственный запрос N+1.

`internal/releasebroker/broker.go` и
`cmd/factory-release-broker/main.go` принимают immutable `operation_id`
(generation id), adapter и commit. Их durable status — единственное
авторитетное доказательство выпуска: одинаковый POST идемпотентен, иной input
конфликтует, неопределённая операция после restart закрывается `failed` без
повторного executor. PID служит диагностикой, а не состоянием восстановления.

`ops/fx-factory-release` получает `FACTORY_DELIVERY_ID` и повторно читает
terminal result вместо второй установки. `ops/systemd/factory-release-broker.service`
задаёт StateDirectory, а `ops/install-project-release-broker.sh` его
устанавливает. `pilot/test_pilot.py`, `internal/releasebroker/broker_test.go`,
`ops/test-fx-factory-release.sh` и `ops/test-install-project-release-broker.sh`
покрывают этот contract. UI, SQLite schema и control plane не входят в область.

## Последовательный план

1. Перед изменением сопоставить текущие generation, intents, waits, receipts и
   outbox в `pilot/pilot.py` с контрактом фаз; не возвращать legacy active flags.
2. Любую новую crash boundary сначала выразить тестом с restart и счётчиками
   merge, broker POST, physical release и owner completion.
3. Сохранять immutable request/status broker до внешнего запуска; менять
   release driver и systemd installer только вместе с их shell fixtures.
4. Проверить N/N+1, `rc=8`, конфликт POST и fail-closed recovery целевыми
   Python, Go и shell тестами; затем выполнить общий регресс один раз.
5. Отдельно подтвердить, что receipt, `mark_final(..., true)` и done-outbox
   возникают только из `completed`, а notification restart не дублирует
   локальную запись.

## Критерии приёмки

| Критерий | Проверяемый результат |
| --- | --- |
| Одна модель | В durable state у поколения ровно одна из пяти фаз; legacy state только audit-only. |
| Честная готовность | Merge/Verify не завершают работу; её завершают receipt и accepted `completed`. |
| Recovery | Сбой после intent, merge, POST, status или outbox не даёт второго merge/release и не теряет wait. |
| N и N+1 | Второй merge при `reserved` присоединён к N; во время запуска создаётся ровно один N+1. |
| Идемпотентность | Повтор POST с тем же id/input возвращает status; другой input конфликтует. |
| Fail-closed | Неавторитетный/неpersisted terminal outcome не создаёт owner done и не запускается повторно. |
| Изоляция | Изменения ограничены Pilot, broker, release driver, systemd/installer и их тестами. |

## Тест-план

- `pilot/test_pilot.py`: table-driven restart после intent, `gh_merge`, journal,
  wait, broker POST, running, terminal status и outbox; проверять все четыре
  счётчика и отсутствие owner done при `failed`.
- `internal/releasebroker/broker_test.go`: disk-backed duplicate/conflicting
  POST, restart в `launching`/`running`, status-before-PID и ровно один
  `FXExecutor.Execute`.
- `ops/test-fx-factory-release.sh`: два вызова с одним
  `FACTORY_DELIVERY_ID` выполняют одну установку и читают один terminal status.
- `ops/test-install-project-release-broker.sh`: installed service получает
  StateDirectory и безопасно обновляет работающий broker.
- Общий регресс перед слиянием: `just check`.

## Риски и решения

- Filesystem, GitHub, broker и push не образуют общую транзакцию. Решение:
  durable intent/receipt/outbox до внешней границы и immutable generation id.
- `rc=8` — занятый внешний lock, а не неуспех. Решение: сохранить N
  `reserved` и повторять только тот же id.
- После restart нельзя доказать жизнь старого process по PID. Решение:
  status-authoritative fail-closed, не усыновлять процесс.
- Legacy `pid`/`launch_token` не имеют надёжной связи с Verify. Решение:
  audit-only migration, никогда не создавать из него новый done.
- Не каждый adapter поддерживает generation status. Решение: такой adapter не
  подтверждает автоматическую готовность владельцу.

## Карточка работы

`knowledge/cards/CARD-0090-merge-release-delivery-state-machine-resumption.md`

## Готово, когда

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл internal/releasebroker/broker.go
ГОТОВО-КОГДА: файл internal/releasebroker/broker_test.go
ГОТОВО-КОГДА: файл cmd/factory-release-broker/main.go
ГОТОВО-КОГДА: файл ops/systemd/factory-release-broker.service
ГОТОВО-КОГДА: файл ops/install-project-release-broker.sh
ГОТОВО-КОГДА: файл ops/test-install-project-release-broker.sh
ГОТОВО-КОГДА: файл ops/fx-factory-release
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: команда python3 -m unittest pilot.test_pilot.MergeReleaseDeliveryStateMachineTests

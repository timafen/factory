# Восстановление отставшей ветки поставки без потери реализации

## Цель и влияние на владельца

Конвейер не должен возвращать готовую работу в разработку только потому, что
ветка поставки была опубликована до большого продвижения `main`: в её
закреплённом сравнении могут отсутствовать все четыре обещанных файла
реализации. Для владельца это означает, что подтверждённый код не теряется и
Review получает одну свежую, проверяемую ветку поставки, а не пустой diff или
необъяснимый повтор Implement.

## Технический подход и реальные файлы

`pilot/pilot.py` уже получает независимый remote-снимок в
`fresh_branch_snapshot()`, хранит исходную реализацию в
`implementation_artifact()` и умеет собрать чистую ветку через
`rebuild_clean_branch()`. Изменение объединит эти факты: если закреплённый
candidate отстаёт от remote default branch и в его diff отсутствуют обещанные
файлы, Pilot должен взять только обещанные пути из подтверждённого
implementation artifact, собрать новую delivery-ветку от свежего default
branch, заново закрепить SHA и продолжить Review только с новым снимком.

`internal/controlplane/promises_http.go` остаётся источником read-only
диагностики обещаний. В нём и в `internal/controlplane/http_test.go` будет
зафиксирован контракт: оператор видит обещанные пути и команду проверки той
же работы, включая случай, когда Pilot запросил пересборку поставки. Никаких
маршрутов записи, UI и изменений схемы SQLite не требуется.

Файлы реализации:

- `pilot/pilot.py`
- `pilot/test_pilot.py`
- `internal/controlplane/promises_http.go`
- `internal/controlplane/http_test.go`

## Последовательный план

1. Дополнить pinned snapshot признаком отставания default branch и точным
   набором отсутствующих promised paths; не использовать cached `origin/main`.
2. В `review_gate()` отличать пустую/неопубликованную реализацию от stale
   delivery: вторую пересобирать только из опубликованного canonical
   implementation artifact и только по promised paths.
3. После push пересобранной ветки повторно вызвать `fresh_branch_snapshot()`;
   при любой ошибке resolution/fetch вернуть только `BLOCKED: review
   infrastructure`, не создавать возврат в Implement и не выполнять merge.
4. Сохранить выбранные branch/head через `record_delivery_artifact()` так,
   чтобы Review, Verify и merge использовали один и тот же pinned candidate.
5. Отразить в read-only promises API состояние обещаний и факт ожидания/успеха
   пересборки без раскрытия SHA или служебных путей в пользовательском ответе.
6. Добавить регрессии на stale delivery с четырьмя promised paths, на пустой
   source artifact, на ошибку повторного fetch и на неизменность обычной
   актуальной ветки.

## Критерии приёмки

1. Отставший candidate, у которого pinned diff не содержит все обещанные
   файлы, получает новую опубликованную delivery-ветку от свежего remote
   default branch; в ней есть только актуальные изменения обещанной области.
2. Пустой, отсутствующий, непроверенный или service candidate не может быть
   источником пересборки и остаётся поводом для прежнего безопасного возврата.
3. После пересборки Review, Verify и auto-merge используют исключительно
   повторно закреплённые base_sha/candidate_sha; сбой remote-проверки блокирует
   конвейер, но ничего не сливает.
4. API обещаний сохраняет обратную совместимость и позволяет оператору
   сопоставить работу, её файлы и обязательную команду проверки.
5. Актуальная delivery-ветка и работы без `implementation_artifact` не меняют
   поведение.

## Тест-план

В `pilot/test_pilot.py` создать bare remote: исходная implementation branch
содержит четыре promised paths, `main` значительно продвигается, а delivery
branch остаётся старой. Проверить пересборку, повторное pinning, отсутствие
лишнего Implement и неизменность выбранного delivery artifact. Отдельно
проверить пустой source и fetch failure. В `internal/controlplane/http_test.go`
проверить read-only ответ promises до и после зафиксированного состояния.

Целевая обязательная команда должна завершаться кодом 0:

`python3 -m unittest -v pilot.test_pilot.FreshDefaultBranchSnapshotTests pilot.test_pilot.RebuiltDeliveryBranchPipelineTests`

## Риски и решения

- Риск: переносить изменения из старой delivery-ветки поверх нового `main`.
  Решение: источником служит только подтверждённая implementation branch, а
  перенос ограничен promised paths.
- Риск: stale branch маскирует посторонний diff. Решение: после rebuild снова
  вычислять pinned scope и применять существующий area gate.
- Риск: сеть меняется между Review и Verify. Решение: оба этапа повторно
  закрепляют remote SHA; ошибки инфраструктуры не превращаются в request
  changes или merge.
- Риск: оператор не понимает причину задержки. Решение: promises API остаётся
  read-only и выдаёт понятное состояние обещаний без внутренних идентификаторов.

## Карточка работы

`knowledge/cards/CARD-0163-stale-delivery-branch-reconciliation.md`

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл internal/controlplane/promises_http.go
ГОТОВО-КОГДА: файл internal/controlplane/http_test.go
ГОТОВО-КОГДА: команда python3 -m unittest -v pilot.test_pilot.FreshDefaultBranchSnapshotTests pilot.test_pilot.RebuiltDeliveryBranchPipelineTests

# CARD-0075 — Готовность работы подтверждается выпуском

## HEAD

- Status: Implemented — ожидает review/verify.
- Branch: `factory/145d1805-ea0-da91db87-ef2`.
- Implementation commit: 54ee2f365c5c49f454e79c36fa37f86cc3bd2696 — финальный PASS и уведомление выдаются только после успешного выпуска.
- What changed: ожидание выпуска сохраняется с задачей и поколением; `rc=0`
  создаёт delivery receipt, а `rc=8`/коалесцирование сохраняют ожидание.
- What changed: эпики и «Сделано недавно» признают готовность только по receipt
  поставки; UI показывает «Ожидает слияния и выпуска».
- Evidence: `python3 -m unittest -v pilot.test_pilot.PostMergeDeployTest pilot.test_pilot.PostMergeDeliveryCompletionTests pilot.test_pilot.EpicCompletionReceiptTests pilot.test_pilot.RecentDoneTest` → 26 OK.
- Evidence: `cd web && npm test -- --run src/Work.test.ts` → 11 passed.
- Next action: Review проверить обработку ошибки выпуска и восстановление состояния на реальном цикле Pilot.

## LOG

### 2026-08-11 — Specification

В `pipeline_watch` финальный PASS и сообщение «Задача выполнена» выдаются
сразу после `gh_merge`, а `deploy_after_merge` только резервирует фоновый
процесс. `poll_post_merge_deploys` знает код выпуска, но не связан с Verify
задачей; `advance_epics` принимает merge journal как окончательный receipt.

Выбран малый устойчивый контракт: сохранить ожидание поставки с task id и
минимальным поколением release, завершать его только после `rc=0`, а `rc=8`
переносить на retry. UI terminal Verify получает явное ожидание вместо
ошибочного «работа завершена». Новый контракт не блокирует цикл Pilot и не
изменяет команды штатного выпуска.

### 2026-08-11 — Implement

`pilot.py` сохраняет ожидание поставки до запуска release и привязывает его к
нужному поколению. Успех создаёт durable receipt, единожды завершает Verify и
уведомляет владельца; lock и ошибка не создают ложный PASS. Эпики, недавние
результаты и Work UI используют подтверждённую поставку. Проверено 26 целевыми
Python-тестами и 11 UI-тестами Work.

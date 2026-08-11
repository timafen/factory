# CARD-0077 — Готовность работы подтверждается выпуском

## HEAD

- Status: Implemented — ожидает review/verify.
- Branch: `factory/d59886f6-4ff-ed449ae5-650`.
- Implementation commit: 2951ac42e9883ecbb34c075388409a1a04bd296e — финальный PASS и уведомление выдаются только после успешного выпуска без повтора уведомления после рестарта.
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

### 2026-08-11 — Implement

Карточка перенумерована с CARD-0075 на CARD-0077: CARD-0075 уже занят
параллельной работой. Реализационный коммит сохранён без изменений; целевые
проверки ссылок, Python- и UI-регрессии подтверждают поставку.

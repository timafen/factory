# CARD-0077 — Готовность работы подтверждается выпуском

## HEAD

- Status: BLOCKED — полный Python-набор содержит не обновлённый регрессионный тест, ожидающий final PASS сразу после merge.
- Branch: `factory/8ea71c92-92b-d672d3bf-043`.
- Implementation commit: 2951ac42e9883ecbb34c075388409a1a04bd296e — финальный PASS и уведомление выдаются только после успешного выпуска без повтора уведомления после рестарта.
- What changed: ожидание выпуска сохраняется с задачей и поколением; `rc=0`
  создаёт delivery receipt, а `rc=8`/коалесцирование сохраняют ожидание.
- What changed: эпики и «Сделано недавно» признают готовность только по receipt
  поставки; UI показывает «Ожидает слияния и выпуска».
- Evidence: целевые `PostMergeDeployTest`, `PostMergeDeliveryCompletionTests`, `EpicCompletionReceiptTests` и `RecentDoneTest` → 26 OK; полный `python3 -m unittest -v pilot.test_pilot` → 190 OK, 1 FAIL (`PipelineWatchMergeTests.test_verify_pass_is_processed_once`).
- Evidence: чистый web-набор после `npm ci`: lint и typecheck OK, 14 файлов/145 тестов OK, production build OK.
- Next action: обновить `PipelineWatchMergeTests.test_verify_pass_is_processed_once` под ожидание выпуска и повторить полный Verify.

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

### 2026-08-11 — Verify

| Критерий | Проверка | Наблюдение |
| --- | --- | --- |
| До успешного выпуска нет ложного завершения | `PostMergeDeliveryCompletionTests` и `Work.test.ts` | PASS: ожидание не закрывается старым поколением, UI показывает «Ожидает слияния и выпуска». |
| Успешный выпуск завершает работу ровно раз | `PostMergeDeliveryCompletionTests` | PASS: один delivery receipt, один final PASS и одно уведомление. |
| Коалесцирование, lock и restart сохраняют границу поколения | `PostMergeDeployTest` и `EpicCompletionReceiptTests` | PASS: 21 целевая проверка. |
| Ошибка выпуска не объявляет работу готовой | `PostMergeDeployTest` | PASS: обработка ненулевого rc и безопасных диагностик покрыта. |
| Обычная завершённая работа остаётся в Done | `web/src/Work.test.ts` в полном `npm test` | PASS: standalone success остаётся в Done; 145 web-тестов зелёные. |
| Полный набор проекта | `python3 -m unittest -v pilot.test_pilot` | BLOCKED: 190/191 OK; `PipelineWatchMergeTests.test_verify_pass_is_processed_once` ожидает `mark_final` непосредственно после merge, что больше не соответствует контракту. |

Дополнительно: `git diff --check` прошёл; lint, typecheck и production build web-пакета прошли после чистой установки зависимостей. Для полного Verify требуется исправить указанную устаревшую проверку.

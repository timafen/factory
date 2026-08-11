# CARD-0077 — Готовность работы подтверждается выпуском

## HEAD

- Status: Implemented — ожидает review/verify.
- Branch: `factory/95bac4a0-123-9e15e522-9f1`.
- Implementation commit: cdd6f5ae9ab2d7ed0087514c31dcbe7751719d1b — рестарт после merge journal восстанавливает единственное ожидание выпуска.
- What changed: Pilot не пропускает выпуск, если остановился между durable merge receipt и `deploy_after_merge`; receipt и `release_failed` не перезапускаются.
- What changed: Сквозная регрессия доказывает один запуск выпуска, PASS только после `rc=0` и отсутствие дублей уведомлений.
- Evidence: `python3 -m unittest -v pilot.test_pilot.PipelineWatchMergeTests pilot.test_pilot.PostMergeDeployTest pilot.test_pilot.PostMergeDeliveryCompletionTests pilot.test_pilot.EpicCompletionReceiptTests` → 27 OK.
- Evidence: `cd web && npm test -- --run src/Work.test.ts` → 12 passed; `npm run lint` → passed; `npm run build` → passed.
- Next action: Review проверить restart между merge journal и `deploy_after_merge` на полном цикле Pilot.

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

### 2026-08-11 — Implement

После terminal failure Pilot записывает для ожидавшего Verify durable
`release_failed`, снимает ложное ожидание и не повторяет уведомление после
рестарта. Work показывает остановленный выпуск с причиной и безопасным
действием. Сквозные Python-сценарии покрывают success, `rc=8`, failure и
restart; Work UI и production build прошли.

### 2026-08-11 — Implement

После merge journal Pilot восстанавливает отсутствующее ожидание поставки до
пропуска повторного merge. Новый сквозной тест моделирует рестарт ровно в этом
окне: выпуск стартует один раз, `final_pass` появляется только после `rc=0`, а
delivery receipt и уведомление не дублируются. Проверены 27 Python-регрессий,
12 Work UI-тестов, ESLint и production build.

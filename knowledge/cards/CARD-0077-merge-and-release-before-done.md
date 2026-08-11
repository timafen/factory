# CARD-0077 — Готовность работы подтверждается выпуском

## HEAD

- Status: Implemented — три crash/queue blocker исправлены, ожидает review/verify.
- Branch: `factory/bb135866-e32-dae98b77-a5d`.
- Implementation commit: 402bbdc59a33d18bb9d2a1f5063cc21d793c60a0 — retry-поколение и доставка итогов устойчивы к рестарту.
- What changed: Новый merge присоединяется к зарезервированному retry после `rc=8`; один успешный запуск закрывает оба ожидания.
- What changed: Receipt, PASS и уведомления разделены; durable outbox с одним ntfy `sequence_id` продолжает успех и ошибку после каждого crash boundary.
- Evidence: `python3 -m unittest -v pilot.test_pilot.PipelineWatchMergeTests pilot.test_pilot.PostMergeDeployTest pilot.test_pilot.PostMergeDeliveryCompletionTests pilot.test_pilot.EpicCompletionReceiptTests` → 33 OK.
- Evidence: `cd web && npm test -- --run src/Work.test.ts` → 12 passed; `npm run build` → passed.
- Next action: Review подтвердить три restart-сценария по новым регрессиям.

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

### 2026-08-11 — Implement

Новый merge после `rc=8` привязывается к уже зарезервированному retry, поэтому
его запуск не теряет successor. Receipt, финальный PASS и уведомления стали
отдельными устойчивыми шагами; pending/delivered outbox и стабильный ntfy
`sequence_id` безопасно продолжают успех и ошибку после рестарта. Проверены 33
целевые Python-регрессии и 12 Work UI-тестов.

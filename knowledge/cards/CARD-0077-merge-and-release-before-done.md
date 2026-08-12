# CARD-0077 — Готовность работы подтверждается выпуском

## HEAD

- Status: READY — `web/dist` пересобран из актуального `Work.tsx` и зафиксирован.
- Branch: `factory/15c34fad-104-aa16b05d-c21`.
- Implementation commit: 6855bf10b35659cafdf51660bb9dfb577d6774f3 — обновлён закоммиченный embedded bundle интерфейса Work.
- What changed: browser bundle теперь содержит карточку завершения, которая ждёт
  подтверждённый выпуск и не закрывает работу по занятому номеру.
- Evidence: сборка и проверка чистоты `dist` → PASS; `just ui-check` → 159/159 PASS.
- Next action: повторить полный browser e2e после исправления нестабильной отдачи
  тестового ZIP-архива.

## LOG

### 2026-08-11 — Implement

Изменение перебазировано на свежий `origin/main`: восстановлены обязательные
fresh snapshot с pinned SHA и BLOCKED при инфраструктурной ошибке, резервирование
и handoff CARD, а также crash-safe delivery state machine. Ожидание успешного
выпуска и CARD-0077 сохранены. Целевые проверки дали 18 Python и 11 UI тестов;
lint, typecheck и build прошли. Полный Vitest выявил один существующий таймаут
`WorkHistory.test.tsx`, не затрагиваемого поставкой.

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

Обновлена `PipelineWatchMergeTests`: успешный merge фиксируется один раз,
но `mark_final` не вызывается до подтверждённого выпуска. Полный Python-набор
прошёл 191 тест; web lint/typecheck/build прошли, полный Vitest имеет таймауты.

### 2026-08-12 — Verify

Pinned snapshot: база `0ec9dd9e3f27a4ef0c5ce8a4503f1ba4d9ef0622`,
кандидат `aebb86e02100ee9191a202e4ed5e6d4bd9e5f94a`.

| Критерий | Команда / проверка | Результат |
|---|---|---|
| 1. До подтверждённого выпуска нет ложного завершения | `python3 -m unittest pilot.test_pilot`; `test_recovery_journals_before_wait_without_second_merge`; `Work.test.ts` | PASS: ожидание сохраняется, UI остаётся активным |
| 2. Успех завершает работу единожды | тот же Python-набор; `test_outbox_and_notification_journals_are_immutable` | PASS: receipt и уведомление не дублируются |
| 3. Занятый выпуск требует следующего поколения | `test_lock_join_and_successor_are_distinct` | PASS: старое поколение не закрывает новый wait |
| 4. Lock/retry переживает рестарт | `test_locked_retry_uses_same_real_broker_operation_after_second_merge` | PASS: повтор использует durable operation |
| 5. Ошибка не создаёт ложный PASS и дубль тревоги | `test_real_rollback_failure_never_completes_waits`; `test_failed_broker_terminal_never_completes_waits` | PASS: ожидания не завершаются |
| 6. Crash/restart не теряет и не дублирует результат | `test_state_file_crash_boundaries_recover_in_fresh_pilot_processes`; `test_terminal_write_failure_survives_real_broker_restart_without_false_done` | PASS: восстановление проходит на всех границах |
| 7. Standalone Done не изменён | `just ui-check` (159 тестов), `Work.test.ts` (11 тестов) | PASS: standalone остаётся Done, terminal Verify ждёт выпуск |

Смежные проверки: Go-пакеты, race, воспроизводимый release, tooling, launcher и
сборка прошли. `just test-browser` заблокирован до Playwright: `npm run build`
создаёт `index-CCEUfF1P.js`, удаляет закоммиченный `index-FbtnAMaY.js` и меняет
`web/dist/index.html`; `git diff --exit-code -- dist` возвращает 1.

### 2026-08-12 — Implement

Пересобран и закоммичен `web/dist` после подтверждения владельца; сборка повторно
подтвердила совпадение артефакта с исходниками. `just ui-check` прошёл: 14 файлов,
159 тестов. Полный browser e2e дошёл до Playwright, но остановился на тестовом
ZIP-потоке: `file data stream has unexpected number of bytes` и обрезанный архив.

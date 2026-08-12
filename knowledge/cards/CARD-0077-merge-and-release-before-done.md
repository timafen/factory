# CARD-0077 — Готовность работы подтверждается выпуском

## HEAD

- Status: Implemented — проверено, ожидает слияния.
- Branch: `factory/ccd1e717-41d-48b32756-1c2`.
- Implementation commit: 9a537b0a79d0ba68ee2ff0cf03ba0363f9c80a72 — сохранены актуальные защиты Review, CARD и crash-safe delivery вместе с ожиданием выпуска.
- What changed: terminal Verify до delivery receipt остаётся активным и показывает
  «Ожидает слияния и выпуска»; успешный выпуск завершает работу единожды.
- What changed: сохранены pinned fresh snapshot, резервирование/передача номера
  карточки и восстановление merge intent до task cursor.
- Evidence: целевые Python-регрессии snapshot/CARD/delivery → 18 OK;
  `npm test -- --run src/Work.test.ts` → 11 OK.
- Evidence: `npm run lint && npm run typecheck && npm run build` → PASS.
- Next action: слить ветку; нестабильный таймаут полного Vitest в существующем
  `WorkHistory.test.tsx` разобрать отдельно.

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

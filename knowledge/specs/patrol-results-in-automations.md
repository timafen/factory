# Патрульные находки — только на экране Automations

## Цель и влияние на владельца

Служебные задачи `Factory Pipeline Patrol` не должны смешиваться с работами владельца: они исчезают из всех разделов Work, включая «Сделано», активные и архивные списки. При этом каждый запуск патруля остаётся наблюдаемым в деталях Automation: видны итоговое состояние, finding/diagnostic и связанная задача, если она была создана. Владелец видит только продуктовую работу в Work и получает объяснимый результат патруля в одном месте.

## Технический подход и реальные файлы

1. В `internal/controlplane/store.go` отфильтровать из `/api/v1/tasks` только задачи, для которых существующие durable-факты классифицируют работу как `workClassPatrol`. Фильтр должен быть частью SQL-выборки/постраничного курсора, чтобы патруль не занимал слот страницы и не возвращался после `next_cursor`; обычные product, scheduled, helper и service задачи сохранить. Использовать существующий `classifyWork` из `internal/controlplane/work_classification.go`, не вводить эвристику по тексту заголовка.
2. В `web/src/Work.tsx` добавить защитную фильтрацию перед `build`/`StageBoard` по тому же признаку, если API-модель уже содержит Automation-классификацию; не менять семантику группировки обычных задач. Удалить путь, по которому patrol получает подпись «Проверка приняла результат».
3. В `web/src/Automations.tsx` сохранить/уточнить строку Runs: каждый occurrence показывает `automationRunState`, `diagnostic`, task title и действие открытия связанной задачи. Не скрывать occurrence без task: отображать его конечное состояние и finding, а для `task_deleted` — явное отсутствие задачи. Пагинация и merge истории должны оставаться идемпотентными после reload.
4. Добавить регрессионные тесты в `web/src/Work.test.ts` и новый `web/src/Automations.test.tsx` (или ближайший фактический тестовый файл экрана), backend-тесты рядом с `internal/controlplane/pipeline_patrol_test.go`/`store_test.go` на фильтрацию и cursor.

## Последовательный план

1. Зафиксировать контракт классификации patrol и SQL-пагинации на уровне control-plane.
2. Реализовать backend-исключение с корректным `LIMIT + 1` и cursor после исключённых строк.
3. Защитить Work и убрать ложный done-текст только для patrol.
4. Проверить отображение state, diagnostic/finding и task-link для первой страницы, следующей страницы и повторной загрузки Automations.
5. Добавить целевые UI/backend тесты и выполнить обязательные проверки.

## Критерии приёмки

- Patrol-задача не появляется ни в одном разделе Work, включая «Сделано», активные и архивные списки.
- Обычные product-задачи и прочие служебные типы не исчезают.
- Фильтрация сохраняется при cursor-пагинации и после полного reload Work.
- Каждый patrol run в Automation detail показывает итоговое состояние и diagnostic/finding; при созданной задаче есть рабочая ссылка/кнопка открытия.
- Run без задачи не теряется, а `task_deleted` отображается явно.
- Для patrol в Work отсутствует «Проверка приняла результат».

## Тест-план

- `web/src/Work.test.ts`: patrol исключён, обычная pipeline/product-задача и другие типы сохранены, done-метка не появляется.
- `web/src/Automations.test.tsx`: состояние, diagnostic, task title/link, отсутствие задачи и пагинация после reload.
- `internal/controlplane/pipeline_patrol_test.go` или `store_test.go`: SQL-фильтр не возвращает patrol, не ломает порядок/cursor и не теряет соседние типы.
- Запустить: `cd web && npm install`; `cd web && npm test -- --run src/Work.test.ts src/Automations.test.tsx`; `cd web && npm run lint`; `cd web && npm run typecheck`; `go test ./internal/controlplane/...`; `git diff --check`.

## Риски и решения

- Если backend-факты для списка задач недоступны на этапе SQL, использовать предварительную выборку с запасом и продолжать cursor до заполнения страницы; не фильтровать по словам в title.
- Двойная фильтрация backend/frontend допустима как защита reload, но должна быть чистой и не менять прочие типы.
- Длинные diagnostic могут ломать строку Runs; ограничить только визуальное оформление, сохранив полный текст в доступном title/деталях.
- Удаление задач из базы, изменение самой логики patrol, расписания и обычных Automations вне объёма.

## Карточка работы

`knowledge/cards/CARD-0098-patrol-results-in-automations.md`

ГОТОВО-КОГДА: файл internal/controlplane/store.go
ГОТОВО-КОГДА: файл web/src/Work.tsx
ГОТОВО-КОГДА: файл web/src/Automations.tsx
ГОТОВО-КОГДА: файл web/src/Work.test.ts
ГОТОВО-КОГДА: файл web/src/Automations.test.tsx
ГОТОВО-КОГДА: команда cd web && npm test -- --run src/Work.test.ts src/Automations.test.tsx

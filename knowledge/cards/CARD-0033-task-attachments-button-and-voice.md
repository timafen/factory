# CARD-0033 — Вложения к задаче из кнопки и голосового сценария

## HEAD

- Status: Verified PASS — ожидает слияния человеком.
- Branch: `factory/66c2762e-cc4-1e85fca1-3d7`.
- Head commit: будет указан завершающим коммитом Verify.
- What changed: `/say` принимает до 5 файлов по 10 МБ; сервер хранит их в
  `/opt/factory-data/attachments/<id-задачи>/`; worker сохраняет одноимённые файлы
  как `<id>-<имя>`; fallback пилота сохраняет исходный ключ привязки файлов.
- Evidence: полный Go-набор, целевые Go/Python-проверки, TypeScript и production
  web build → PASS. Полный Vitest сохраняет один известный сбой notification
  groups в неизменённом `Settings.test.tsx`; полный ESLint — 9 известных ошибок.
- One next action: влить ветку в `main`.

## LOG

### 2026-08-08 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Кнопка выбирает до пяти файлов, показывает размер и позволяет удалить файл | `cd web && npx vitest run src/TaskFilePicker.test.tsx src/App.test.tsx` | PASS: picker и сценарий блокировки отправки во время upload/создания задачи проходят. |
| UI передаёт вложения без поломанной сборки | `cd web && npx tsc -p tsconfig.app.json --noEmit && npx vite build` | PASS: TypeScript без ошибок, production bundle собран. |
| Сервер ограничивает и хранит вложения, выдаёт их только владельцу lease | `go test ./internal/controlplane ./internal/worker ./internal/protocol` | PASS: проверены лимит/размер, запрет executable, MIME по содержимому, откат при ошибке, SHA-256 и materialization worker. |
| Голосовой fallback сохраняет ключ привязки файлов | `python3 -m unittest pilot.test_pilot` | PASS: 1 тест проводит два ID вложений через обе fallback-ступени. |
| Смежный полный Go-набор | `go test ./...` | PASS. |
| Смежный полный frontend-набор | `cd web && npm test`; `npm run lint` | Не блокирует: Vitest 1 падение в неизменённом `Settings.test.tsx` (устаревшее ожидание `notify_groups`); ESLint 9 прежних ошибок в Access, Live, Pipeline и Say. |


### 2026-08-08 — Specification

Создана спецификация `knowledge/specs/task-attachments-button-and-voice.md`.
Проверка исходного кода показала, что оба текущих пути создают задачу только с
текстовым prompt: `DelegateModal` отправляет JSON в `/api/v1/tasks`, а `/say`
передаёт в intake только аудио и текст. В Control Plane нет модели, API или
доставки файлов в worktree. Поэтому план включает минимальный сквозной контракт
вложений, а не декоративный file input.

### 2026-08-08 — Implement

Первый узкий фрагмент добавляет в `Delegate task` доступный выбор нескольких
файлов, список имени и размера и удаление отдельного файла. Пока серверное
хранилище, лимиты и доставка worker не реализованы, форма не создаёт задачу с
таким выбором и сообщает об этом рядом с вложениями — файл не теряется и не
выдаётся за доставленный. `TaskFilePicker.test.tsx` и изолированный App-сценарий
прошли; TypeScript и production build прошли. Полный Vitest имеет один старый
сбой `Settings.test.tsx`: тест ожидает устаревший набор notification groups.

### 2026-08-08 — Implement

После утверждения владельцем зафиксированы лимиты 5 файлов по 10 МБ, хранение
под каталогом данных Factory в подпапке ID задачи и запрет исполняемых файлов.
Добавлены multipart upload, атомарная привязка метаданных, lease-защищённая
выдача worker, проверка SHA-256 и материализация в `.factory/attachments`.
Оба UI-маршрута используют общий picker и показывают русскую причину отказа;
неудачные незавершённые загрузки подчищаются. Целевые Go-тесты, полный Vitest,
TypeScript и production build прошли после слияния со свежим `origin/main`.

### 2026-08-08 — Implement

Закрыт контракт созданной голосовой задачи: Control Plane записывает файлы в
`/opt/factory-data/attachments/<id-задачи>/` и добавляет абсолютный путь каждого
файла в context строкой `ВЛОЖЕНИЕ:`. Изолированный тест проверяет путь хранения
и его видимость в возвращаемой карточке задачи.

### 2026-08-08 — Implement

После Review устранены коллизии одинаковых исходных имён: worker использует
имя `<id-вложения>-<исходное-имя>` и показывает тот же путь агенту. Перемещения
blob при создании задачи теперь компенсируются в обратном порядке при ошибке
`Rename`, обновления БД или `Commit`; тест с удалённым вторым source-файлом
доказывает возврат первого blob и откат `task_id`. Полный Go-набор, целевые
регрессии, TypeScript, picker-тест и production web build прошли.

### 2026-08-08 — Implement

По суженному решению владельца кнопка `Delegate task` теперь недоступна с начала
загрузки файлов до завершения создания задачи, а сервер игнорирует заявленный
клиентом MIME и определяет его по первым байтам содержимого. UI- и Go-регрессии,
TypeScript, production build и заданные пакеты Go прошли; полный Vitest сохраняет
известный несвязанный сбой ожидания notification groups.

### 2026-08-08 — Implement

Fallback-маршрутизация пилота больше не создаёт новый `request_key`: голосовая
задача во всех трёх попытках сохраняет ключ, к которому Control Plane привязал
файлы. Новый Python-тест проводит два вложения через обе fallback-ступени.
TypeScript и production build прошли; полный Vitest сохраняет известный сбой
notification groups, полный Go-набор — несвязанный 404 managed catalog.

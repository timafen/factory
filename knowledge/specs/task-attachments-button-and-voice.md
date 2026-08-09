# Спецификация: прикрепление скриншотов и файлов из кнопки и голоса

## Goal and user impact

Владелец сможет приложить скриншоты и обычные файлы к задаче как из окна
`Delegate task`, так и из голосового маршрута `/say`. После подтверждения задача
поступит исполнителю вместе с исходными файлами, а не только с упоминанием их
имён в prompt. Это позволит поручать исправление UI по скриншоту и разбор
логов/документов без внешнего ручного обмена файлами.

## Текущее поведение и граница задачи

- `web/src/DelegateModal.tsx` собирает форму и через `web/src/api.ts` посылает
  JSON `CreateTaskInput` в `POST /api/v1/tasks`; поля для файлов нет.
- `web/src/Say.tsx` отправляет только аудио в `/intake/transcribe`, а после
  подтверждения — JSON proposal в `/intake/commit`.
- `intake/app.py` собирает текстовый context и вызывает `pilot.create_task`.
- `internal/protocol/types.go` и `internal/controlplane/http.go` принимают только
  JSON; `CreateTaskRequest` допускает лишь text `description`/`context` до
  64 KiB. Worker получает только prompt. Следовательно, base64 в context не
  подходит: скриншот быстро превысит лимит и не создаст полезного файла в
  worktree.

## Technical approach

Добавить в Control Plane task-scoped attachments как отдельный ресурс и
материализовать их в worktree до запуска агента.

1. Новый authenticated multipart endpoint загрузки принимает файл до создания
   задачи, сохраняет blob вне prompt и возвращает opaque `attachment_id`, исходное
   имя, MIME type и размер. Незавершённая загрузка принадлежит `request_key` и
   удаляется по TTL, если задача не создана.
2. Расширить JSON create-task contract массивом `attachment_ids`; создание
   атомарно привязывает только уже загруженные вложения того же request key.
   Ответ/TaskDetail возвращает метаданные без содержимого.
3. Расширить claim, чтобы worker скачивал каждое вложение по аутентифицированному
   endpoint, проверял размер/хеш и записывал его в
   `.factory/attachments/<безопасное-имя>` в подготовленном worktree. В prompt
   добавить короткий список относительных путей и инструкцию ознакомиться с
   ними; двоичные данные в prompt не вставлять.
4. В `web/src/api.ts` вынести upload helper (multipart, progress/ошибки) и
   расширить input создания task IDs вложений. `DelegateModal` показывает file
   picker, очередь выбранных файлов, имя/размер, удаление до отправки и не
   создаёт задачу, пока upload не завершён.
5. В `web/src/Say.tsx` использовать тот же UI-компонент/хелпер: выбор файлов
   доступен до записи и сохраняется при распознавании, редактировании proposal и
   подтверждении. При `commit` он передаёт IDs через intake.
6. В `intake/app.py` принять attachment IDs в proposal/`CommitIn`, передать их
   в `pilot.create_task`; для эпика явно решить семантику ниже.

### Affected modules/files

- UI: `web/src/Say.tsx`, `web/src/DelegateModal.tsx`, `web/src/api.ts`, новые
  целевые Vitest-тесты и, при извлечении общего picker, новый локальный компонент.
- Intake: `intake/app.py` и его тесты.
- Контракт и сервер: `internal/protocol/types.go`, `internal/controlplane/http.go`,
  `internal/controlplane/store.go`, миграция SQLite и HTTP/store tests.
- Доставка: protocol claim и `internal/worker/attempt_lifecycle.go` (либо
  ближайший существующий загрузчик worker) с интеграционным тестом.

### Данные и API

Предлагаемый минимум:

- `POST /api/v1/task-attachments` — multipart `file`, `request_key`; ответ
  `{id, name, content_type, size, sha256}`. Сервер не доверяет client MIME/name.
- `POST /api/v1/tasks` — добавляет `attachment_ids?: string[]`; прежние запросы
  без поля полностью совместимы.
- `Task`/`TaskDetail` и worker claim получают только attachment metadata и IDs;
  download endpoint выдаёт содержимое исключительно назначенному worker для
  конкретной попытки. Хранилище содержит blob, размер, SHA-256, исходное имя,
  создание/привязку и состояние очистки.

Предлагаемые стартовые ограничения: максимум 10 файлов, 25 MiB на файл, 50 MiB
на задачу; отклонять пустые файлы, дубликаты IDs и превышение лимитов до создания
задачи. Имя при записи очищать от path traversal/коллизий. Тип файла не
фильтровать: задача заявлена для файлов вообще; содержимое никогда не исполнять.

## Plan

1. Утвердить лимиты, backing storage и семантику эпиков из раздела «Риски».
2. Добавить protocol-модели, схему/миграцию и Store-операции upload, attach,
   list, authorisation/download и TTL cleanup; покрыть HTTP/store тестами.
3. Передать metadata в task detail/claim и материализовать verified blobs в
   `.factory/attachments` до старта runtime; добавить worker integration test.
4. Добавить API helper и единый picker в `DelegateModal`; протестировать выбор,
   удаление, upload failure и payload создания.
5. Добавить тот же выбор в `/say`, сохранить IDs через proposal и `commit`;
   протестировать передачу в intake и обычный голосовой путь без файлов.
6. Запустить целевые тесты, TypeScript и затронутые Go-тесты; выполнить ручной
   smoke обоих UI-маршрутов с изображением и текстовым файлом.

## Acceptance criteria

### Кнопка постановки задачи

- В `Delegate task` можно добавить несколько файлов, увидеть их имена и размеры,
  удалить любой до отправки и создать задачу без вложений как раньше.
- После успешного создания назначенный worker находит каждый файл по объявленному
  относительному пути; screenshot не сериализован в текст prompt.
- Ошибка upload/лимита показана рядом с вложением и не создаёт частичную задачу.

### Голосовой сценарий

- На `/say` пользователь выбирает файлы вместе с голосовым запросом; выбор не
  теряется при transcription, dispatch, refinement и до `commit`.
- Подтверждённая одиночная задача получает те же файлы, что и кнопочный маршрут.
- Голосовой сценарий без файлов продолжает работать без изменения API-результата.

### Безопасность и совместимость

- Вложение недоступно произвольному пользователю или другому worker; проверяются
  принадлежность request/task/attempt, размер и SHA-256.
- Невалидные IDs, чужой request key, path traversal, пустые/слишком большие файлы
  возвращают контролируемую 4xx ошибку; созданная задача остаётся без orphan blob.
- Все существующие клиенты `POST /api/v1/tasks` остаются валидными.

## Test plan

- UI: Vitest для `DelegateModal` и `Say`: files selected/removed, upload IDs
  присутствуют в create/commit, ошибки и старый путь без files.
- Intake: unit/API test `CommitIn` передаёт IDs в `pilot.create_task`.
- Server: HTTP и Store tests для upload, ownership, attach atomically, limits,
  cleanup и metadata-only responses.
- Worker: integration test создаёт задачу с fixture blobs и подтверждает наличие,
  содержимое и безопасные имена файлов в `.factory/attachments` до runtime.
- Commands: `cd web && npx tsc -p tsconfig.app.json --noEmit`; целевые Vitest;
  `go test ./internal/controlplane ./internal/worker ./internal/protocol`.

## Risks and decisions requiring approval

1. **Scope expansion required.** Одни `Say.tsx`, `DelegateModal.tsx`, `api.ts` и
   `intake/app.py` не могут доставить бинарный файл remote worker. Реализация
   должна изменить Control Plane, persistent storage и worker. Отвергнутый
   вариант — base64 в context: он ломает 64 KiB/72 KiB limits и не создаёт файл.
2. **Storage/retention.** Нужны явные ответ: SQLite blobs (простая поставка, но
   рост базы) или filesystem/object storage (лучше для объёма, нужен lifecycle).
   Предлагается filesystem storage под data directory плюс DB metadata, удаление
   orphan uploads по TTL и task attachments вместе с retention task.
3. **Эпик.** Один голосовой proposal может создать несколько дочерних задач.
   Предлагается прикреплять полный набор к каждой дочерней задаче; это проще для
   исполнителя, но умножает storage/logical references. Нужна санкция владельца.
4. **Limits.** Предложенные 10 × 25 MiB, 50 MiB/task — продуктовая гипотеза,
   требующая утверждения с учётом диска и сети worker. До него не следует
   реализовывать фиксированные production limits.
5. **Не входит в первый выпуск.** Drag-and-drop, clipboard paste image, previews,
   OCR и антивирус — отдельные улучшения; scope creep не включать.

## Card

`knowledge/cards/CARD-0033-task-attachments-button-and-voice.md`

## Проверяемые обещания

ГОТОВО-КОГДА: файл `web/src/Say.tsx`

ГОТОВО-КОГДА: файл `web/src/DelegateModal.tsx`

ГОТОВО-КОГДА: файл `web/src/api.ts`

ГОТОВО-КОГДА: файл `intake/app.py`

ГОТОВО-КОГДА: файл `internal/protocol/types.go`

ГОТОВО-КОГДА: файл `internal/controlplane/http.go`

ГОТОВО-КОГДА: файл `internal/controlplane/store.go`

ГОТОВО-КОГДА: файл `internal/worker/attempt_lifecycle.go`

ГОТОВО-КОГДА: команда `cd web && npx tsc -p tsconfig.app.json --noEmit`

ГОТОВО-КОГДА: команда `go test ./internal/controlplane ./internal/worker ./internal/protocol`

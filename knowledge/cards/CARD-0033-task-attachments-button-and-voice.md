# CARD-0033 — Вложения к задаче из кнопки и голосового сценария

## HEAD

- Status: Implement complete — сквозная доставка готова и проверена.
- Branch: `factory/d31c6388-715-ad51e9ca-6ad`.
- Head commit: `d405f6b` (реализация слита со свежим `origin/main`).
- What changed: `/work` и `/say` загружают до 5 файлов по 10 МБ; сервер хранит
  их в каталоге ID задачи. Worker скачивает по действующей lease, сверяет размер
  и SHA-256 и кладёт в `.factory/attachments` до запуска runtime.
- Evidence: `go test ./internal/controlplane ./internal/worker ./internal/protocol`,
  полный Vitest, TypeScript и production build → PASS.
- One next action: провести Review сквозного контракта и пользовательских ошибок.

## LOG

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

Implementation commit: 613cf6a95ba114ef347daeede01cd8ca07b0f898 — API скрывает вопросы с Python mock repr, сохраняя исходные JSON-записи.

# CARD-0108 — Скрыть Python `MagicMock` из вопросов production dashboard

## HEAD

- Статус: Implement + Test завершены; фильтр API реализован.
- Ветка: `factory/e781259d-ef1-c692f311-4e5`.
- Спецификация: `knowledge/specs/production-dashboard-hides-python-magicmock-question.md`.
- Implementation commit: `613cf6a95ba114ef347daeede01cd8ca07b0f898`.
- Что изменено: `GET /api/v1/questions` исключает канонический `<MagicMock ...>` /
  `<Mock ...>` только из владелец-видимых полей; исходные записи не меняются.
- Evidence: `go test ./internal/controlplane` → PASS; `git diff --check` → PASS.
- Следующее действие: выполнить финальный rebase на свежий `main`, полный build и push.

## LOG

### 2026-08-12 — Specification

В production-каталоге подтверждена запись «Исправить корзину»: поля `situation`
и `question` содержат строковое представление результата
`deep_diagnose().get()` типа `MagicMock`. `listQuestions` сейчас без проверки
отдаёт JSON, а `Answer.tsx` отображает полученный текст.

Определена защита на серверной границе списка вопросов: записи с точной формой
Python mock repr не включаются в `GET /api/v1/questions`, но не удаляются с
диска. Обычное упоминание слова `MagicMock` остаётся видимым. Отдельный тест
должен воспроизвести production-форму, сохранить нормальный вопрос и доказать,
что в HTTP body нет mock repr.

Номер `CARD-0108` проверен после обновления свежего `origin/main` и всех
опубликованных веток: `CARD-0105`, `CARD-0106` и `CARD-0107` заняты другими
работами, а номер и этот путь свободны.

### 2026-08-12 — Implement

На ветке `factory/e781259d-ef1-c692f311-4e5` добавлен read-only фильтр API и HTTP-регрессия: production-подобный вопрос с mock repr скрывается, обычный вопрос и текст о `MagicMock` возвращаются, JSON на диске сохраняется. Проверено `go test ./internal/controlplane -run TestListQuestionsHidesPythonMockRepresentations`, `go test ./internal/controlplane` и `git diff --check`.

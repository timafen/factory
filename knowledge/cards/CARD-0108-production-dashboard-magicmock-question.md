Implementation commit: fc3af293e5e2b2c3802ad9b1d376f7796aa3b067 — Pilot-тесты перенесены из live data во временный `FACTORY_DATA_HOME`, поэтому новые тестовые вопросы не загрязняют production.

# CARD-0108 — Скрыть Python `MagicMock` из вопросов production dashboard

## HEAD

- Статус: Specification завершена; реализация API-фильтра ожидается.
- Ветка: `factory/69ea8390-df8-b744463e-40a`.
- Спецификация:
  `knowledge/specs/production-dashboard-hides-python-magicmock-question.md`.
- Влияние: владелец не увидит Python mock repr вместо вопроса; нормальные
  вопросы и история решений сохранятся.
- Область реализации: `internal/controlplane/questions_http.go` и новый
  `internal/controlplane/questions_http_test.go`; UI и production JSON не
  изменяются.
- Следующее действие: на этапе Implement добавить узкий read-only фильтр API и
  целевой HTTP-тест, затем заменить строку `Implementation commit` на commit
  этой реализации.

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

# CARD-0131 — «Сделано недавно»: влитое отдельно и даты по-человечески

Implementation commit: 92249bc3b72e20194da28e69eaba5376d0317e60 — подтверждённые слияния и остановки разделены, даты и причины понятны владельцу.

## HEAD

- Status: Implemented.
- Branch: `factory/595f144c-1ce-4b89e067-dbf`.
- Implementation commit: 4a1bbef467c2aa6faf58b9e307be823a46abfe13 — служебные данные исключены из причин остановки.
- What changed: обзор принимает только безопасные строки `ДОКАЗАТЕЛЬСТВО:`/`ПРОВЕРКА:` без task_id, SHA и PID.
- What changed: небезопасный или нераспознанный результат заменяется нейтральной причиной; добавлен регрессионный тест.
- Evidence: `python3 -m unittest -v pilot.test_pilot.RecentDoneTest` → 7 tests OK; Overview → 30 tests passed, typecheck/build passed.
- Evidence: frontend full suite → 179 tests passed; `go test ./...` → all packages passed. Python full suite → 2 pre-existing correction-restart failures.
- Next action: повторно запустить Review для опубликованной ветки-кандидата.

## LOG

### 2026-08-13 — Implement

Серверный контракт разделён на подтверждённые receipt-слияния и `failed`/`cancelled`
остановки с независимым лимитом пяти записей. Интерфейс показывает человеческие
даты, этап и причину, а контрактная и UI-регрессии подтверждают, что пять новых
провалов не скрывают четыре влитые работы.

### 2026-08-13 — Implement

Причина остановки теперь извлекается только из безопасной помеченной строки;
сырой результат с task_id, SHA или PID заменяется нейтральным текстом.
Регрессионный тест подтверждает отсутствие этих данных; целевые и frontend/Go
проверки зелёные, в полном Python-наборе остаются две прежние ошибки восстановления.

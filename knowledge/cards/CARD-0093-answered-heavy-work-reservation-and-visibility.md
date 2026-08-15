# CARD-0093 — резерв отвеченной тяжёлой работы

Implementation commit: 79c455feb80edc3a83f3b421614dbad409d3b72a — отвеченная тяжёлая работа получает durable-резерв слота и видимое ожидание

## HEAD

Status: Implemented
Branch: factory/dc07dd7f-4a7-51261301-9dd
Implementation commit: 79c455feb80edc3a83f3b421614dbad409d3b72a — отвеченная тяжёлая работа получает durable-резерв слота и видимое ожидание
What changed: Pilot сохраняет резерв в записи отвеченного вопроса, восстанавливает его после рестарта и не пропускает новую тяжёлую работу раньше ответа. Answer, Overview и Work объясняют ожидание без нового запроса к владельцу.
Evidence: `python3 -m unittest pilot.test_pilot` → 342 passed (13 skipped); `npx vitest run src/Answer.test.tsx src/Overview.test.ts src/WorkView.test.tsx` → 39 passed; `npx tsc -p tsconfig.app.json --noEmit` → passed.
Next action: Review целевой поставки.

## LOG

### 2026-08-15 — Implement

Перенесено только целевое резервирование на свежий `main`, без удалений механизмов восстановления, release-train и их тестов. Резерв переживает перезапуск, отдаёт приоритет ответу владельца и отображает понятную причину ожидания.

### 2026-08-15 — Implement

Проверена совместимость очистки устаревших вопросов с локальными расширениями прежнего интерфейса. Полный набор Pilot прошёл: 342 проверки, 13 пропущены.

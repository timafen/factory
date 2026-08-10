# CARD-0055 — Ускорить самые медленные тесты воркера

## HEAD

Implementation commit: c715e1250f3246c604e00fbabc67059d3e4a9c92 — четыре медленных интеграционных теста ускорены без удаления сценариев или проверок.

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/8305b7d7-3e0-26fa0923-f51`.
- What changed: репозитории создаются из очищаемого неизменяемого шаблона;
  pool cancellation, supervisor lease и task timeout используют короткие
  тестовые интервалы; 11 reconciliation-сценариев делят server/store/repository.
- Evidence: целевой 35-секундный барьер — PASS, пакет 28,193 с, команда 30 с;
  `go test -count=1 ./...` на Verify — PASS, все пакеты, 141,50 с целиком.
- One next action: человек проверяет и вливает ветку.

## LOG

### 2026-08-10 — Implement

Общий Git-шаблон копируется в отдельные checkout и bare origin; новая регрессия
подтверждает разные remote identity и независимость опубликованных refs. Пул
сохраняет 10 одновременных попыток и queued refill, но замечает отмену через
100 мс. Server-loss остаётся настоящей потерей последней аренды с итогом `lost`,
а timeout по-прежнему убивает игнорирующую SIGTERM process group таймером задачи.

Обязательный целевой запуск прошёл за 30,918 с внутри Go (32 с целиком). Пять
uncached-прогонов timeout прошли за 7,94–8,43 с каждый; пять повторных server-loss
прогонов после настройки SQLite busy timeout прошли за 6,58–7,27 с каждый.
Связанные Git/barrier-регрессии прошли: 4 теста за 7,647 с.

После пяти устойчивых прогонов task timeout сокращён до секунды: каждый прогон
запустил настоящую дочернюю process group и прошёл за 6,90–7,26 с. Финальный
35-секундный барьер после rebase прошёл за 28,193 с внутри Go и 30 с целиком.

### 2026-08-10 — Verify

| Критерий | Проверка | Наблюдение |
| --- | --- | --- |
| 10 слотов, queued refill и изоляция runtime | полный `go test -count=1 ./...` | PASS; `internal/worker` 129,555 с |
| 11 reconciliation-сценариев | полный `go test -count=1 ./...` | PASS; табличный тест входит в `internal/worker` |
| Независимые Git fixture | полный набор и регрессия `TestRepositoryFixturesFromTemplateAreIsolated` | PASS; удалённые origin и refs изолированы |
| Четыре цели не дольше 35 секунд | сохранённый целевой барьер из реализации | PASS: 28,193 с в Go, 30 с целиком |
| Server-loss и task timeout | полный `go test -count=1 ./...` | PASS; package assertions не ослаблены |
| Нет runtime/API/миграционных изменений | `git diff --name-only origin/main...HEAD` | изменены только тесты и knowledge |

Полный некэшированный прогон Verify: `go test -count=1 ./...` — PASS, 141,50 с
целиком; лог: `/tmp/factory-card-0055-go-test.log`.

# CARD-0094 — Общий бюджет слотов worker-служб

Implementation commit: 11c7234abe150302571946247e5da4813c2cad54 — сервер настраивает и атомарно применяет общий бюджет worker-слотов

## HEAD

- Status: Implemented and verified.
- Branch: `factory/f05c4df4-156-406ce6e0-066`.
- What changed: `host_max_concurrent` по умолчанию равен числу логических CPU,
  принимает положительный override и передаётся в Store при старте сервера.
  `Claim` атомарно ограничивает все непросроченные preparing/running lease;
  локальная ёмкость worker остаётся независимой.
- Evidence: `go test ./... -count=1` — PASS; `go build ./...` — PASS;
  `git diff --check` — PASS.
- One next action: провести review и влить ветку в `main`.

## LOG

### 2026-08-12 — Specification

Фактический код подтвердил, что каждая worker-служба ограничена только своим
каналом `Manager.slots`, а единый loopback control plane уже сериализует выдачу
attempt в SQLite. Спецификация закрепляет общий предел в `Store.Claim`: на двух
worker с локальной ёмкостью 10 первые восемь lease выдаются, девятый остаётся
пустым; terminal или истёкший lease освобождает место.

Настройка `host_max_concurrent` размещена в server config, потому что один server
координирует все worker-процессы узла. Без настройки используется
`runtime.NumCPU()`; явные неположительные значения отклоняются. Понижение лимита
после рестарта не убивает живые попытки, но запрещает новые до естественного
drain. UI, БД, registration и локальный диапазон `max_concurrent` не меняются.

Номер `CARD-0094` проверен по свежему `origin/main` и 769 опубликованным remote
refs; путей с этим номером не было.

### 2026-08-15 — Implement

Сервер читает `host_max_concurrent`, использует число видимых CPU при отсутствии
поля и не стартует при нуле или отрицательном значении. Общая проверка в одной
SQLite-транзакции теперь использует этот бюджет, поэтому две службы не могут
суммарно превысить лимит машины; terminal и истёкший lease освобождают слот.
Проверены config default/override/reject, общий предел, освобождение и локальная
ёмкость worker; `go test ./... -count=1`, `go build ./...` и `git diff --check` прошли.

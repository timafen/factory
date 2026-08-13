# CARD-0094 — Общий бюджет слотов worker-служб

Implementation commit: 6cef241a78a6a7e8361c7325c9d9ca44729f0ef6 — общий бюджет слотов ограничивает выдачу задач мощностью машины

## HEAD

- Status: Specification complete — ready for Implement + Test.
- Specification: `knowledge/specs/host-worker-slot-budget.md`.
- Owner decision: не более 8 одновременно выполняемых задач суммарно на
  восьмиядерном узле; `max_concurrent` остаётся локальным пределом службы.
- Delivery: общий настраиваемый server-side бюджет по умолчанию равен числу
  логических CPU и атомарно проверяется при выдаче lease всем worker-службам.
- One next action: реализовать server config и общий admission в транзакции
  `Store.Claim`, затем выполнить указанную в спецификации целевую команду.

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

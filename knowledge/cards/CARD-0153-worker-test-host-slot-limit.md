# CARD-0153 — Тестовый host-лимит возвращает выпускные проверки воркера

Implementation commit: ожидается на этапе Implement — продуктовый код на этапе Specification не изменялся.

## HEAD

- Status: Specified — ready for Implement + Test.
- Specification: `knowledge/specs/worker-test-host-slot-limit.md`.
- Owner impact: выпускной Go-барьер должен снова проходить независимо от числа
  CPU test host, сохраняя production-защиту и исходный масштаб проверок.
- Scope: test-only открытие control plane Store и две worker fixtures; без CLI,
  HTTP, protocol, environment или runtime-настроек.
- Related contracts: CARD-0098 (production host budget), CARD-0055 (пул из 10 и
  быстрые worker-тесты), CARD-0096 (lease/heartbeat для 10 попыток).
- Next action: реализовать спецификацию и заменить эту строку полным SHA отдельного
  implementation-коммита, который меняет файлы вне `knowledge/cards/`.

## LOG

### 2026-08-13 — Specification

На свежем `main` обычный `controlplane.Open` задаёт общий предел активных lease
через `runtime.NumCPU()`. Две worker fixtures используют этот production-путь,
хотя одна последовательно создаёт 11 lease для всех reconciliation cases, а
другая требует 10 одновременных attempts. На восьмиядерном host последние claims
пусты, поэтому оба теста и полный выпускной прогон падают.

Зафиксирован минимальный подход: test-only конструктор внутреннего Store принимает
явный положительный лимит до создания handler; обычный `Open`, `Claim` и fallback
`runtime.NumCPU()` не меняются. Только две целевые fixtures выбирают лимиты
`len(cases)` и `10`. Проверки обязаны пройти отдельно без cache, после чего полный
`go test -count=1 ./...` выполняется ровно один раз.

CARD-0153 свободна в `origin/main` и во всех 927 опубликованных ветках на момент
спецификации. CARD-0098 не изменяется: это карточка прежнего production-лимита,
а не текущей тестовой регрессии.

# CARD-0090 — Приёмка десяти полных работ без ручного ремонта

Implementation commit: 0ec9dd9e3f27a4ef0c5ce8a4503f1ba4d9ef0622 — текущая кодовая база Factory с группировкой работ, русскими статусами и безопасной историей этапов.

Status: Specification — реализация и десять прогонов ещё не начинались.

Scope: только внутренний сервис Factory; торговая система, production, данные и
секреты исключены.

Owner-approved sequence:

1. Русские названия всех статусов.
2. Человеческие названия релизов.
3. Единый непротиворечивый итог работы.
4. Понятное следующее действие остановленной работы.
5. Фильтр «Нужно решение владельца».
6. Русская хронология этапов.
7. Длительность этапов и всей работы.
8. Понятные пустые состояния и ошибки.
9. Копирование диагностического отчёта без секретов.
10. Автоматические проверки этих правил интерфейса.

Gate: следующую работу запускать только после разработки, проверки, merge в
`main` и штатного `fx factory release` предыдущей; всего должно быть ровно 10.

Evidence required: target tests, browser-visible result, release result and proof
that no manual state/data repair was used. Previous triage branch
`factory/a274d10c-2bd-00edbfab-4fb` was not available on origin, so nothing was
copied from it.

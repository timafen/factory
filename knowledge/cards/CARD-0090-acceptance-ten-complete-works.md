# CARD-0090 — Приёмка десяти полных работ без ручного ремонта

## HEAD

Status: In progress — реализован общий русский слой статусов, времени и ошибок.

Branch: `factory/94e03ee1-79f-9e8fe697-202`

Implementation commit: fea7f929293cc622c701b9a7273ec47a4ec7aef0 — собран поставляемый интерфейс с русскими статусами, временем и безопасными ошибками.

What changed:

- Общие подписи статусов безопасны к неизвестным backend-значениям.
- Время, длительности и state loading/error русские; API error не раскрывает сырой текст.

Evidence: web tests 183/183; TypeScript, lint, web build и `go build ./...` → успешно.

Next action: подключить единый итог и действие владельца к списку и detail работы.

## LOG

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

### 2026-08-15 — Implement

Общий форматтер теперь выдаёт русские названия известных состояний и «Неизвестно»
для новых значений backend. Экранные загрузка и ошибки переведены на русский,
а текст ошибки API не выводится пользователю. Полный `web` test suite, TypeScript,
lint и production build завершились успешно.

### 2026-08-15 — Implement

Работа перенесена на свежий `origin/main`, а полный UI-набор приведён к безопасным
русским ошибкам без сырого текста API. Проверено: 183/183 web-теста, TypeScript,
lint, production web build и Go build завершились успешно.

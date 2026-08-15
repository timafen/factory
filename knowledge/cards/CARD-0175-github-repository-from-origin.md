Implementation commit: 9f414dd1298e61641633cae05c9dadac564d3379 — Pilot вызывает `gh repo view` с позиционным репозиторием из origin.

# CARD-0175: GitHub-репозиторий Pilot только из origin

## HEAD

Status: Implemented.
Branch: `factory/1c5c6741-43a-0ebf7035-d70`.
Implementation commit: 9f414dd1298e61641633cae05c9dadac564d3379 — `gh repo view` использует поддерживаемый позиционный repository из origin.
What changed: resolver SSH/HTTPS `origin` по-прежнему задаёт цель всех действий;
диагностический CLI-путь теперь реально исполним и не обращается к default-repo.
Evidence: 9 целевых и 350 полных Pilot-тестов → OK; живой bare-вызов вернул
`owainlewis/factory`, позиционный вызов — `timafen/factory`; browser-critical → 5 passed.
Next action: Review подтверждает итоговый diff перед слиянием.

## LOG

### 2026-08-15 — Implement

Исправлен источник идентичности GitHub: `origin` рабочей копии нормализуется
для SSH и HTTPS, а неявный `gh repo view` запрещён. Регрессии воспроизводят
чужой ответ `owainlewis/factory`, проверяют explicit `timafen/factory` и
безопасный отказ для недоступного либо неподдерживаемого remote.

### 2026-08-15 — Implement

Подключение завершено: все GitHub-действия, запускаемые главным циклом, получают
цель из managed `origin`; сторонний `remote_identity` остаётся только описанием.
Регрессии для чужого `owainlewis/factory` и весь `pilot.test_pilot` проходят.

### 2026-08-15 — Implement

Устранён невалидный синтаксис диагностического `gh repo view`: репозиторий из
`origin` передаётся позиционно. Тест проверяет полный массив аргументов процесса;
повторный Verify на свежем `origin/main` и живое сравнение bare/explicit прошли.

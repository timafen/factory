Implementation commit: ea7ae6497ed6ee8907c2d3e254a90c3e87da22a7 — Pilot получает GitHub-репозиторий из origin и блокирует чужой контекст gh.

# CARD-0175: GitHub-репозиторий Pilot только из origin

## HEAD

Status: Implemented.
Branch: `factory/6d5e4825-036-7d294239-11c`.
Implementation commit: ea7ae6497ed6ee8907c2d3e254a90c3e87da22a7 — Pilot получает GitHub-репозиторий из origin и блокирует чужой контекст gh.
What changed: добавлен resolver SSH/HTTPS `origin` в `owner/repo` и explicit
`--repo` для диагностического `gh repo view`; bare-вызов и несовпадающий ответ
теперь безопасно останавливают действие.
Evidence: `python3 -m unittest pilot.test_pilot` → OK (346 tests, 13 skipped).
Next action: Review проверяет, что поставка ограничена resolver, регрессиями и этой карточкой.

## LOG

### 2026-08-15 — Implement

Исправлен источник идентичности GitHub: `origin` рабочей копии нормализуется
для SSH и HTTPS, а неявный `gh repo view` запрещён. Регрессии воспроизводят
чужой ответ `owainlewis/factory`, проверяют explicit `timafen/factory` и
безопасный отказ для недоступного либо неподдерживаемого remote.

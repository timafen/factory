Implementation commit: ea7ae6497ed6ee8907c2d3e254a90c3e87da22a7 — Pilot получает GitHub-репозиторий из origin и блокирует чужой контекст gh.

# CARD-0175: GitHub-репозиторий Pilot только из origin

## HEAD

Status: Implemented.
Branch: `factory/9feaa5f8-af6-4c723584-32a`.
Implementation commit: a57b7041c48423d741ab4a8676a7c60b4afa0855 — Pilot адресует GitHub API, PR и merge только репозиторием из origin.
What changed: resolver SSH/HTTPS `origin` теперь подключён к карте целей главного
цикла; `remote_identity` control plane не может направить API или merge в чужой repo.
Evidence: `python3 -m unittest pilot.test_pilot` → OK (348 tests, 13 skipped).
Next action: Review проверяет сквозной путь API/merge с чужим default-repo `gh`.

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

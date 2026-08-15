# CARD-0164 — `gh` не подменяет зарегистрированный origin

## HEAD

Implementation commit: a34f3f77d9eb671ba56cbd6b59de7d4ea5d46327 — после `gh repo clone` зарегистрированный GitHub URL закрепляется за `origin` до проверки и публикации кэша.

Status: Verified
Branch: `factory/e5b0d18f-eae-811e86c6-04a`.

Factory добавляет отсутствующий либо заменяет неверный `origin`, не удаляя
оставленный `gh` remote `upstream`. Ошибка настройки не публикует cache entry.

Evidence: целевой managed-task test → PASS; ошибки `remote add`/`set-url` → PASS;
`go test -timeout 5m ./...` → PASS; `go build ./...` → PASS;
`just test-browser-critical` через server sandbox → PASS.

Next action: просмотреть и слить реализацию в `main`.

## LOG

### 2026-08-15 — Specification

`gh repo clone` в centrally managed repository может оставить `upstream` более
подходящим remote, чем зарегистрированный `origin`. Для Factory это нарушает
контракт: base branch и код задачи должны быть получены только из identity,
назначенной control plane.

Implement нормализует `origin` из валидированного managed GitHub slug до
первой проверки repository identity. Регрессионный integration test воспроизведёт
клон с `upstream` и докажет, что task использует зарегистрированный origin.

Полная спецификация, файлы реализации и обязательная команда находятся в
`knowledge/specs/managed-worktree-gh-origin-precedence.md`.

### 2026-08-15 — Implement

После клонирования Factory перечисляет remotes и безопасно выполняет `remote add`
либо `remote set-url` для канонического URL зарегистрированного slug. Регрессия
использует разные репозитории для `origin` и `upstream`, проверяет выбранный base
commit и отсутствие опубликованного кэша при обеих ошибках нормализации.

Доказательство: обязательный целевой тест и негативные подслучаи прошли;
полный `go test -timeout 5m ./...` и `go build ./...` завершились успешно.

### 2026-08-15 — Implement

Повторная проверка подтвердила реализацию и исправила стабильную строку статуса
в HEAD карточки, из-за отсутствия которой машинная проверка возвращала работу.
Целевые сценарии выбора `origin` и отказа публикации кэша снова прошли.

### 2026-08-15 — Implement

В проверочной среде восстановлен изолированный browser launcher и повторена
обязательная проверка кандидата. `just test-browser-critical` завершилась с
PASS через server sandbox; тем самым снят прежний инфраструктурный блокер.

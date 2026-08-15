Implementation commit: отсутствует — этап Specification не меняет продуктовый код; реализационный коммит будет добавлен этапом Implement до финальной карточки.

# CARD-0167: идентичность GitHub-репозитория только из origin

## HEAD

Status: Specified.
Branch: `factory/07c2b18e-7d5-3a2022f0-57c`.
What changed: определён безопасный переход от неявного контекста `gh` к
явному репозиторию, полученному из `origin` рабочей копии.
Evidence: на свежем `origin/main` воспроизведён bare-ответ
`owainlewis/factory` при `origin=github.com/timafen/factory`; спецификация
требует explicit `--repo timafen/factory` и регрессию этого расхождения.
Next action: Implement добавляет resolver и целевые тесты из спецификации.

## LOG

### 2026-08-14 — Specification

Проблема не относится к UI или настройкам GitHub CLI: bare `gh repo view`
может использовать сохранённый CLI-контекст, который не совпадает с remote
назначенной рабочей копии. Безопасный контракт — считать `origin` единственным
источником repo identity, нормализовать его и передавать repo явно во все
GitHub-действия. Несовпадение должно блокировать действие до внешней мутации.

Полный план, реальные файлы, критерии и обязательная проверка находятся в
`knowledge/specs/gh-repository-identity-from-origin.md`.

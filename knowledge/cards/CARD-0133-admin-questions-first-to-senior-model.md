Implementation commit: c73d41932c405164564e6ff7183cf3dbaa5f1896 — разрешённые admin-вопросы направляются старшей модели, а owner видит только явные эскалации.

# CARD-0133 — Административные вопросы сначала решает старшая модель

## HEAD

- Status: Implemented; targeted verification PASS.
- Branch: `factory/e8a75949-f10-22845d23-c9a`.
- Implementation commit: `c73d41932c405164564e6ff7183cf3dbaa5f1896` — admin-маршрутизация и защита capacity от неэскалированных audit-записей.
- What changed: разрешённый staging-вопрос сначала обрабатывает старшая модель через фиксированный `fx` argv; owner получает только записи с `owner_only`.
- Evidence: `AdminQuestionRoutingTests` — 11/11 PASS; HTTP и capacity-регрессии — PASS; `go build ./...` — PASS.
- Next action: Review проверяет diff и опубликованную ветку.

## LOG

### 2026-08-13 — Implement

Поставка собрана от свежего `origin/main`. Канонический `hasOpenOwnerQuestion()`
исключает выполняющиеся и ошибочные admin-аудиты без `owner_only`, поэтому они не
выдают ложный сигнал о необходимости ответа владельца. Целевые Python-регрессии,
HTTP/capacity тесты и сборка Go прошли.

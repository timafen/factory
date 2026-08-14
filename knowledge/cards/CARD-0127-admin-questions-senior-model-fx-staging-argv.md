# CARD-0127 — Старшая модель для административных вопросов

## HEAD

Status: Implemented
Branch: factory/fb639232-586-d3bc45ad-f09
Implementation commit: a03262c9a3990a59e701a2e691bab6724188425c — каждый admin-вопрос сначала проходит senior bridge с фиксированными argv и stdin, обычная модель получает его только после fallback
What changed: senior-маршрут перенесён в начало `route_question`; тест закрепляет порядок `senior → ordinary`, точный argv и полный stdin payload.
Evidence: целевые senior-тесты — 4/4 PASS; весь Pilot — 299 тестов, 13 skipped, PASS; `go test -timeout 5m ./...`, `go build ./...`, syntax/compile checks — PASS.
One next action: повторить Review изменения порядка маршрутизации.

## LOG

### 2026-08-14 — Implement

Добавлен senior-разбор административных эскалаций через строго заданный `sudo -n /usr/local/bin/fx staging brain admin-question --model=...`; вопрос передаётся только через stdin, модель и payload ограничены. Мост staging принимает только этот подмаршрут и allowlist имени модели. Ненулевой exit, timeout, пустой или невалидный JSON безопасно оставляют вопрос владельцу.

Доказательство: `python3 -m unittest pilot.test_pilot` — 299 тестов, 13 skipped; целевые проверки argv/stdin/fallback — 4/4; `go test -timeout 5m ./...`, `go build ./...`, web lint/typecheck/180 тестов/build, `py_compile`, `bash -n ops/fx`, `git diff --check` — PASS.

### 2026-08-14 — Implement

После замечания Review senior bridge перенесён перед всеми обращениями к обычному оркестратору. Новый тест воспроизводит fallback и доказывает порядок вызовов, точный `fx staging brain admin-question` argv и полный JSON в stdin.

Доказательство: `python3 -m unittest pilot.test_pilot.SeniorAdminQuestionTests` — 4/4 PASS; `python3 -m unittest pilot.test_pilot` — 299 тестов, 13 skipped, PASS; `go test -timeout 5m ./...`, `go build ./...`, `bash -n ops/fx`, `py_compile`, `git diff --check` — PASS.

# CARD-0127 — Старшая модель для административных вопросов

## HEAD

Status: Implemented; rebased on fresh origin/main
Branch: factory/e5e89597-f7d-fb81014d-09b
Implementation commit: 4640f3cc6c634459c6e959e1c67cafce23a32fda — каждый admin-вопрос сначала проходит senior bridge с фиксированными argv и stdin, обычная модель получает его только после fallback
What changed: senior-маршрут перенесён в начало `route_question`; тест закрепляет порядок `senior → ordinary`, точный argv и полный stdin payload.
Evidence: `SeniorAdminQuestionTests` — 4/4 PASS; `bash -n ops/fx`, `py_compile`, `go test` и `go build ./internal/protocol` — PASS.
One next action: провести повторный Review закреплённого снимка на свежем origin/main.

## LOG

### 2026-08-14 — Implement

Добавлен senior-разбор административных эскалаций через строго заданный `sudo -n /usr/local/bin/fx staging brain admin-question --model=...`; вопрос передаётся только через stdin, модель и payload ограничены. Мост staging принимает только этот подмаршрут и allowlist имени модели. Ненулевой exit, timeout, пустой или невалидный JSON безопасно оставляют вопрос владельцу.

Доказательство: `python3 -m unittest pilot.test_pilot` — 299 тестов, 13 skipped; целевые проверки argv/stdin/fallback — 4/4; `go test -timeout 5m ./...`, `go build ./...`, web lint/typecheck/180 тестов/build, `py_compile`, `bash -n ops/fx`, `git diff --check` — PASS.

### 2026-08-14 — Implement

После замечания Review senior bridge перенесён перед всеми обращениями к обычному оркестратору. Новый тест воспроизводит fallback и доказывает порядок вызовов, точный `fx staging brain admin-question` argv и полный JSON в stdin.

Доказательство: `python3 -m unittest pilot.test_pilot.SeniorAdminQuestionTests` — 4/4 PASS; `python3 -m unittest pilot.test_pilot` — 299 тестов, 13 skipped, PASS; `go test -timeout 5m ./...`, `go build ./...`, `bash -n ops/fx`, `py_compile`, `git diff --check` — PASS.

### 2026-08-15 — Implement

Реализация перенесена на свежий `origin/main` без изменения области: senior-маршрут остаётся первым, использует фиксированный `fx staging brain admin-question --model=…` argv и передаёт JSON только через stdin. Карточка привязана к фактическому кодовому коммиту до её обновления.

Доказательство: `python3 -m unittest pilot.test_pilot.SeniorAdminQuestionTests` — 4/4 PASS; `bash -n ops/fx`; `python3 -m py_compile pilot/pilot.py`; `go test -timeout 5m ./internal/protocol`; `go build ./internal/protocol` — PASS. Закреплённый diff от `origin/main` чист по whitespace и содержит только шесть файлов задачи.

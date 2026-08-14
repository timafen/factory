# CARD-0127 — Старшая модель для административных вопросов

## HEAD

Status: Implemented
Branch: factory/68a31679-a66-bcd43e07-f3a
Implementation commit: 8e40455a9af16e7519ed6ec0d9a8b60054d4ab53 — admin-вопросы проходят через строгий `fx staging` senior-маршрут, а его настройки принимаются серверной схемой Pilot
What changed: добавлен фиксированный argv bridge с безопасным stdin payload; успешные answer/wait сохраняют текущую семантику, ошибки остаются owner-эскалацией; schema sync принимает новые поля.
Evidence: `python3 -m unittest pilot.test_pilot` — 299 тестов, 13 skipped; `go test -timeout 5m ./...` — PASS; `go build ./...` — PASS.
One next action: после выката проверить один безопасный административный вопрос на staging через разрешённый bridge.

## LOG

### 2026-08-14 — Implement

Добавлен senior-разбор административных эскалаций через строго заданный `sudo -n /usr/local/bin/fx staging brain admin-question --model=...`; вопрос передаётся только через stdin, модель и payload ограничены. Мост staging принимает только этот подмаршрут и allowlist имени модели. Ненулевой exit, timeout, пустой или невалидный JSON безопасно оставляют вопрос владельцу.

Доказательство: `python3 -m unittest pilot.test_pilot` — 299 тестов, 13 skipped; целевые проверки argv/stdin/fallback — 4/4; `go test -timeout 5m ./...`, `go build ./...`, web lint/typecheck/180 тестов/build, `py_compile`, `bash -n ops/fx`, `git diff --check` — PASS.

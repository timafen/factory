# CARD-0048 — Изолировать сеть серверного браузера

## HEAD

- Status: Implement PASS — ожидает слияния.
- Branch: `factory/baf3534c-87e-bdcb1358-8b8`.
- Head commit: `d106859` — изоляция серверного браузера после rebase на `main`.
- What changed: Chromium работает в deny-by-default systemd BPF scope; доступны
  только `factory.timafen.com`, `staging-automation.tarser.net` и loopback.
- Delivery: installer проверяет BPF до изменений, атомарно ставит полный комплект,
  выполняет allow/deny smoke со screenshot; release делает этот gate обязательным.
- Evidence: installer/release tests — PASS; Go — PASS; UI 123/123; tooling,
  launcher и сборка двух бинарей — PASS; shell syntax/`git diff --check` — PASS.
- Known baseline: общий `just check` останавливается на двух прежних staticcheck
  findings в `internal/controlplane`; изменённые browser/release файлы не затронуты.
- Host check: user systemd bus недоступен, passwordless sudo отсутствует; поэтому
  root-проба встроена в installer и при неподдерживаемом BPF останавливает выпуск.
- One next action: слить доставленную ветку и выполнить штатный release на Factory host.

## LOG

### 2026-08-10 — Implement

Утверждены единственные разрешённые FQDN: `factory.timafen.com` и
`staging-automation.tarser.net`; loopback оставлен техническим исключением.
Добавлен root helper с systemd BPF allowlist без browser DNS, proxy override и
доступа к production/внешнему интернету.

Installer доказывает действие политики на локальном сокете до изменения файлов,
затем ставит launcher/helper/config/sudoers как один откатываемый комплект.
Smoke открывает два разрешённых адреса, сохраняет screenshot и требует отказа
для `automation.tarser.net` и `example.com`. Release включает этот smoke как
обязательный gate и откатывает server/worker при отказе.

Целевые проверки installer и release прошли. Интерактивная проверка systemd BPF
в текущей сессии невозможна без root и user bus; это не обходится ослаблением:
на целевом выпуске root-проба обязательна. При её отказе предложен отдельный
network namespace с deny-by-default nftables как равноценная будущая замена.

Полный `just check` дошёл до staticcheck и выявил две существующие ошибки вне
области карточки (`cards_http.go:37`, `pilot_config.go:136`). Остальные проверки
запущены отдельно: Go, UI 123/123, tooling, launcher и сборка двух бинарей прошли.

# CARD-0048 — Изолировать сеть серверного браузера

## HEAD

- Status: Implement PASS — оба обхода закрыты, ожидает слияния.
- Branch: `factory/78242a74-6a0-4df57466-3dc`.
- Head commit: `8035180` — проверенная реализация после rebase на `main`.
- What changed: после allowlist FQDN resolver блокирует все остальные имена;
  Chromium всегда работает с `--no-proxy-server`, proxy/resolver overrides отклоняются.
- Delivery: installer проверяет BPF до изменений, атомарно ставит полный комплект,
  выполняет allow/deny smoke со screenshot; release делает этот gate обязательным.
- Evidence: installer/release negative tests — PASS; Go — PASS; UI 123/123;
  tooling, launcher и сборка двух бинарей — PASS; shell syntax/`git diff --check` — PASS.
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

### 2026-08-10 — Implement

Закрыты два выявленных обхода: resolver rules завершаются
`MAP * ~NOTFOUND`, а Chromium принудительно получает `--no-proxy-server`.
Все пользовательские resolver/proxy overrides отклоняются до запуска браузера.

Отрицательные installer и release tests прошли; Go, UI 123/123, tooling,
launcher и сборка двух бинарей также прошли. Общий `just check`
останавливается только на двух прежних staticcheck findings вне этой области.

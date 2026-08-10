# CARD-0048 — Изолировать сеть серверного браузера

## HEAD

- Status: Implement PASS — замечания Review исправлены, готово к повторному Review.
- Branch: `factory/95ae34c5-fbd-ecb206ad-67a`.
- Head commit: `6b3b35e` — исправление запуска и обходов после rebase на `main`.
- What changed: transient scope получает только поддерживаемые `IPAddress*`;
  `NoNewPrivileges` задаётся через `setpriv --no-new-privs`.
- Chromium-аргументы нормализуются по пробелам и одно-/двухдефисному префиксу,
  поэтому resolver/proxy overrides отклоняются до запуска браузера.
- Evidence: реальный parser `systemd-run` — PASS; installer smoke и отрицательные
  тесты — PASS; release gate — PASS; сборка server/worker — PASS.
- Host check: root BPF-smoke нельзя выполнить в Factory-контейнере из-за внешнего
  `no_new_privs`; installer сохраняет обязательную fail-closed пробу на целевом хосте.
- One next action: передать доставленную ветку на повторный Review.

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

### 2026-08-10 — Implement

Из transient scope удалены неподдерживаемые service-свойства; запрет новых
привилегий перенесён в совместимый `setpriv`. Реальный `systemd-run` теперь
принимает полный набор свойств scope без `Unknown assignment`.

Фильтр повторяет нормализацию POSIX-аргументов Chromium и закрывает одно-дефисные
и whitespace-варианты resolver override. Installer smoke, отрицательные тесты,
release gate, shell syntax и сборка обоих бинарей прошли.

# CARD-0048 — Изолировать сеть серверного браузера

## HEAD

- Status: Verified PASS — ожидает решения человека о слиянии.
- Branch: `factory/2c4889a4-55f-4a730bb4-33a`.
- Head commit: `8b7f7d1` — записаны доказательства защиты серверного браузера.
- What changed: `systemd-run` больше не раскрывает environment после фильтра;
  resolver/proxy и sandbox-disable switches отклоняются до запуска Chromium.
- BPF listener живёт до конца проверки; запуск без `IPAddress*` обязан достичь
  контрольного адреса и завершить отрицательное утверждение ошибкой.
- Evidence: installer smoke, release gate и launcher — PASS; Go 202 s; UI 123/123.
- Full check: format, vet, vuln, boundary, Go, UI, tooling, launcher и build — PASS.
  `staticcheck` останавливается на двух прежних findings вне области; browser E2E
  падает на существующей недоступной опции Repository после 1/18 сценариев.
- Host check: прямой root BPF-smoke недоступен в Factory-контейнере (`uid=994`);
  installer по-прежнему fail-closed требует его на целевом server systemd-хосте.
- One next action: выполнить root installer на целевом systemd-хосте перед merge.

## LOG

### 2026-08-10 — Verify

| Критерий | Команда | Наблюдение |
| --- | --- | --- |
| Изолированный launcher и allowlist | `bash ops/test-install-server-browser.sh` | PASS: разрешены два FQDN и loopback; production и внешний адрес заблокированы; rollback проверен. |
| Release gate и откат | `bash ops/test-fx-factory-release.sh` | PASS: installer обязателен, отказ возвращает прежние binaries. |
| Chromium sandbox smoke | `bash ops/test-browser-sandbox.sh` | PASS. |
| Полный набор | `just check`; затем оставшиеся recipes после `npm ci` | Все составляющие PASS, кроме двух старых staticcheck findings вне области; UI browser E2E упал в несвязанном Workflow сценарии. |
| Живая BPF-проверка | `bash ops/test-systemd-browser-firewall.sh` | Ожидаемый fail-closed отказ: текущий контейнер не root (`uid=994`). |

Проверены adjacent paths: `npm ci` не меняет lockfile, `just build` проходит,
а 18-сценарный Playwright run не дошёл до результата из-за существующего UI race
на отключённом Repository option. Сетевая проверка остаётся обязательной на
целевом root systemd-хосте и не ослабляется в контейнере.

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

### 2026-08-10 — Implement

Закрыты три замечания Review. Вызов `systemd-run` получил
`--expand-environment=no`, а regression test доказывает, что literal `${TERM}`
не превращается после фильтрации в resolver override. Launcher отклоняет
upstream Chromium switches `no-*-sandbox`, `disable-*-sandbox`, управляемый тип
sandbox и sandbox-feature overrides.

BPF listener теперь работает до завершения изолированного и контрольного
запусков. Контроль без `IPAddress*` обязан достичь host endpoint и упасть на
отрицательном утверждении; mock без root проверяет чувствительность smoke.
Installer smoke и release gate прошли, сборка server/worker прошла. Полный
`just check` остановился на прежних findings вне области:
`cards_http.go:37` (U1000) и `pilot_config.go:136` (SA4006).

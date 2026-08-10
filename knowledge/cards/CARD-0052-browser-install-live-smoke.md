# CARD-0052 — Установить браузер без рестарта воркеров

## HEAD

- Status: READY — browser smoke не принимает HTML-страницы ошибок за Factory.
- Branch: `factory/69b00ee2-402-3994b263-654`.
- Implementation commit: 0ffec74081e0a9c481ba7101b30316b477b1c71c — HTTP-статус и title Factory обязательны для live smoke.
- What changed: loopback и staging требуют 2xx; public Factory с credentials
  требует 2xx и title с `Factory`. Без credentials допускается только точный
  `ERR_INVALID_AUTH_CREDENTIALS`; installer и standalone используют один сценарий.
- Evidence: `bash -n ops/install-server-browser.sh ops/test-browser-sandbox.sh
  ops/test-install-server-browser.sh` — PASS; `bash ops/test-install-server-browser.sh` — PASS.
- One next action: проверить и слить заменяющий PR #90 (supersedes #86).

## LOG

### 2026-08-10 — Implement

Независимый review PR #86 выявил, что проверка одного body принимала HTML 401.
Общий сценарий теперь требует `Response.ok()` и, для авторизованного public
Factory, узнаваемый title; 401/403/5xx, неправильный title и 401 без challenge
падают. Fake Playwright покрывает Response/status/title, а installer сохраняет
credentials только в environment без их значений в events или arguments.

`bash -n` трёх изменённых shell-скриптов и `bash ops/test-install-server-browser.sh` — PASS.

### 2026-08-10 — Verify

Ветка получена от implementation без переключения рабочего branch. Трёхточечный
diff от `origin/main` содержит семь заявленных файлов, `git diff --check` чист.

`bash ops/test-install-server-browser.sh` доказывает `NEEDRESTART_MODE=l`, отсутствие
`systemctl restart`, systemd BPF allowlist, sandbox smoke и rollback. Release-suite,
110 Pilot-тестов, Go-тесты и UI-проверки прошли; UI component suite: 123 теста.

Проверка настоящих AppArmor profile, systemd BPF scope и Chromium остановлена до
изменения машины: worker uid не root, а `sudo -n true` возвращает запрос пароля.
Это блокирует утверждение живого smoke, но не является падением реализации.

### 2026-08-10 — Implement

На серверной модели воспроизведён `No usable sandbox`: Ubuntu AppArmor запрещал
unprivileged user namespaces. Installer теперь ставит проверяемый профиль для
точного Playwright Chromium, не отключая sandbox и `--no-new-privs`.

Регрессия доказывает `NEEDRESTART_MODE=l`, отсутствие `systemctl restart`, два
разрешённых FQDN, блокировку production/интернета и resolver/proxy bypass, а
также отсутствие новых launcher, helper, config, sudoers и AppArmor profile
после ошибки. Release возвращает rc=7, откатывает binaries и не скрывает stderr.

`just check`, 104 Pilot-теста, installer/release shell suites и сборка двух Go
бинарей завершились успешно. В `main` перед началом была версия `2ce0f8d`.

### 2026-08-10 — Implement

После замечания Review публикация произвольного 12-КБ хвоста заменена точным
allowlist безопасных сообщений установщика Chromium. Неизвестные строки теперь
заменяются нейтральной отметкой, а не проходят через неполный blacklist.

`python3 -m unittest pilot.test_pilot.PostMergeDeployTest` — 13/13 PASS;
полный `python3 -m unittest pilot.test_pilot` — 110/110 PASS. Adversarial-тест
проверяет AWS key, client_secret, URL credentials, cookie и session.

### 2026-08-10 — Implement

После замечания Review нормализация перенесена в настоящий installer: штатный
`test-browser-sandbox.sh` ловит отказ исполняемого Chromium, installer публикует
только статическую строку `No usable sandbox`, а исходный stderr не выходит наружу.
Release-stub больше не создаёт эту диагностику искусственно; интеграционный тест
проверяет реальный failure-path и полный откат browser-комплекта.

`bash ops/test-install-server-browser.sh`, `bash ops/test-fx-factory-release.sh`
и 13 тестов `PostMergeDeployTest` — PASS. TypeScript-check и production build —
PASS. Diff от `origin/main` не содержит двух посторонних controlplane-файлов.

### 2026-08-10 — Implement

Живой smoke теперь загружает DOM `127.0.0.1:7337` и staging, а достижимость
защищённого Basic Auth публичного Factory признаёт только по успешному DOM или
точному `net::ERR_INVALID_AUTH_CREDENTIALS`. Другие коды закрывают установку,
скрывают сырой stderr и откатывают browser-комплект.

`bash ops/test-install-server-browser.sh`, release-suite, Pilot 110/110,
Go tests, UI 123/123 и `just build` прошли. Полный `just check` остановлен двумя
прежними staticcheck-диагностиками вне diff; эти controlplane-файлы не возвращались.

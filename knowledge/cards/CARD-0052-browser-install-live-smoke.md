# CARD-0052 — Установить браузер без рестарта воркеров

## HEAD

- Status: Implemented PASS — замечание Review устранено, готово к повторному Review.
- Branch: `factory/90b2fdd8-3bf-36abeb90-5cf`.
- Head commit: `79eb5d0` — проверенная реализация до записи карточки.
- What changed: installer нормализует фактический `No usable sandbox` в статическую
  строку и не публикует Chromium stderr; интеграционный тест проходит через штатный
  browser smoke. Обе посторонние правки controlplane исключены из diff.
- Evidence: installer/release shell suites PASS; Pilot 13/13 PASS;
  `npx tsc -p tsconfig.app.json --noEmit` PASS; `npm run build` PASS.
- One next action: Review повторно проверяет достижимость диагностики и чистоту diff.

## LOG

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

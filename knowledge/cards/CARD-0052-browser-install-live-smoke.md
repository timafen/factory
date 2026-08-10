# CARD-0052 — Установить браузер без рестарта воркеров

## HEAD

- Status: Implemented PASS — замечание устранено, готово к повторному Review.
- Branch: `factory/a377b8bd-fd1-ec442943-ded`.
- Head commit: `198afb8` — безопасная диагностика Pilot и adversarial-тесты.
- What changed: install-deps использует needrestart list-only; AppArmor разрешает
  user namespace только закреплённому full Chromium, а весь комплект откатывается
  при ошибке smoke. Pilot публикует только точные строки fail-closed allowlist.
- Evidence: Pilot 110/110 PASS; adversarial-проверка закрывает AWS,
  client_secret, URL credentials, cookie и session.
- One next action: Review проверяет fail-closed allowlist; root smoke остаётся Verify.

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

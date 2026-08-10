# CARD-0052 — Установить браузер без рестарта воркеров

## HEAD

- Status: Implemented PASS — передано на Verify.
- Branch: `factory/72a41a50-4bb-7d27fd60-1d3`.
- Head commit: `c04e163` — installer и проверки живого sandbox smoke.
- What changed: install-deps использует needrestart list-only; AppArmor разрешает
  user namespace только закреплённому full Chromium, а весь комплект откатывается
  при ошибке smoke. Pilot сохраняет безопасный диагностический хвост выпуска.
- Evidence: `just check` — PASS (Go worker 238.8 s, UI 123/123); Pilot 104/104;
  installer и release rollback smoke — PASS; server/worker build — PASS.
- One next action: Verify повторяет root installer smoke на целевом systemd-хосте.

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

# CARD-0051 — Проверить изоляцию сети серверного браузера

## HEAD

- Status: Verified PASS — ожидает решения человека о слиянии.
- Branch: `factory/2c4889a4-55f-4a730bb4-33a`.
- Verified source: `8b7f7d1` — записаны доказательства защиты серверного браузера.
- Evidence: installer, release gate и sandbox smoke прошли; Go 202 s и UI 123/123.
- One next action: root installer smoke на целевом systemd-хосте до merge.

## LOG

### 2026-08-10 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Fail-closed BPF и allowlist | `ops/test-install-server-browser.sh` | PASS; проверены разрешения, запреты, `--no-proxy-server`, запрет expansion и rollback. |
| Обязательная установка в release | `ops/test-fx-factory-release.sh` | PASS; отказ installer откатывает binaries. |
| Sandbox smoke | `ops/test-browser-sandbox.sh` | PASS. |
| Общая регрессия | `just check`, `ui-check`, tooling, launcher, build | PASS, кроме двух старых staticcheck findings вне области. |

Прямая `test-systemd-browser-firewall.sh` отказалась без root (`uid=994`), что
подтверждает fail-closed поведение. Полный Playwright browser набор остановился
на несвязанном существующем сценарии: Repository option недоступна при delegate
Workflow; 1 сценарий прошёл, 16 не запускались.

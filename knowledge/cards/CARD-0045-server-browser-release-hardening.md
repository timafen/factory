# CARD-0045 — Серверный браузер в штатном выпуске Factory

## HEAD

- Status: Implemented + targeted tests/build PASS; live root release is blocked by worker isolation.
- Branch: `factory/2e2c7c6e-d60-0e0250d9-e0e`.
- Head commit: `fd7bd52` (`Дать первому выпуску установить безопасный браузер`).
- What changed: installed helper now runs a syntax-checked, root-owned copy of
  the exact candidate helper; one-time bootstrap installs `fx`, both helpers
  and browser-sandbox as one rollback unit.
- What changed: agents and `/dialog` capture only the approved stand through an
  isolated Chromium namespace and allowlist proxy.
- Evidence: dispatch/bootstrap/release rollback shell tests — PASS; targeted Go
  packages — PASS; UI 60/60, lint, typecheck and Go/UI production builds — PASS.
- Live evidence: `/usr/local/lib/fx-factory-release` is old and browser launcher
  is absent; `sudo -n true` is denied by container `no new privileges`.
- One next action: from a root-capable Factory host run the committed bootstrap,
  standard release, `browser-sandbox check`, then capture the stand on `/dialog`.

## LOG

### 2026-08-09 — Implement

Функция заново собрана от свежего `origin/main` без файлов прежней ветки вне
области. Закрыты замечания Review: выпуск ставит системные команды и sandbox,
Go-runner и launcher ограниченно завершают всё дерево Chromium, а сетевой check
доказывает блокировку TCP/UDP/DNS по firewall counter вместо таймаута ответа.
Полные Go/UI тесты, сборки и целевые shell-проверки прошли; живая root-проверка
невозможна внутри worker-контейнера из-за обязательного `no new privileges`.

### 2026-08-09 — Implement

После повторного Review прокси переведён с `0.0.0.0` на адрес создаваемого для
захвата приватного veth; всем CONNECT-соединениям назначен дедлайн, а hijacked
сокеты учитываются и закрываются при завершении. Выпуск теперь сохраняет весь
системный комплект до первой замены и возвращает его вместе с бинарями при
ошибке или сигнале. Failure-тесты доказали восстановление существовавших файлов
и удаление файлов, которых до неудачного выпуска не было; целевые Go/UI/shell
проверки, lint и обе сборки прошли.

### 2026-08-09 — Implement

Работа заново собрана от свежего `origin/main` только из файлов серверного
браузера. Закрыт blocker первого выпуска: установленный helper передаёт выпуск
root-owned копии helper точного commit кандидата, а отдельный bootstrap единым
откатываемым комплектом ставит `fx`, helpers и browser-sandbox. Новые shell-
регрессии проверяют точную ревизию, повреждённый helper, сбой install/check,
сигнал и отсутствие прежних файлов; Go/UI проверки, lint и сборки прошли.
Живой root-выпуск невозможен в worker-контейнере из-за `no new privileges`.

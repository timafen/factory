# CARD-0045 — Серверный браузер в штатном выпуске Factory

## HEAD

- Status: Implemented; tests and builds PASS; live root release remains blocked
  because the assigned worker still enforces `no new privileges`.
- Branch: `factory/f6583879-c65-8cb38bff-be3`.
- Head commit: `548a650` (`Дать агентам безопасный снимок утверждённого стенда`).
- What changed: the standard release installs `fx`, exact-candidate helpers and
  browser-sandbox as one rollback unit; agents and `/dialog` capture only the
  approved stand through an isolated Chromium namespace and allowlist proxy.
- Evidence: full Go suite — PASS; UI 123/123, lint, typecheck and Go/UI builds —
  PASS; four bootstrap/release/dispatch shell suites — PASS.
- Live evidence: `sudo -n /usr/local/bin/fx whoami` is denied before `fx` starts:
  the assigned container reports that `no new privileges` prevents sudo.
- One next action: after merge, run `fx factory release`, `browser-sandbox check`
  and a real stand capture from the approved root-capable Factory host.

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

### 2026-08-09 — Implement

Работа ещё раз собрана от свежего `origin/main`, причём из прежней ветки взяты
только 31 файл области CARD-0045. Полный Go-набор, 123 UI-теста, lint, typecheck,
обе production-сборки и четыре shell-сценария прошли. Утверждённая живая проверка
не стартовала: выданный worker по-прежнему блокирует штатный
`sudo -n /usr/local/bin/fx` флагом `no new privileges`; ручной обход не применялся.

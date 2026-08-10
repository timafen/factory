# CARD-0045 — Серверный браузер в штатном выпуске Factory

## HEAD

- Status: Implemented and locally verified; do not repeat Review until the
  trusted transition and following `origin/main` release pass on the host.
- Branch: `factory/e7cf0b36-4cb-21448632-2b7`.
- Head commit: `6aed44b` (`Дать агентам безопасно видеть утверждённый стенд`).
- What changed: agents and `/dialog` capture the approved stand through isolated
  Chromium; `fx factory install-release-helper <commit>` installs root-owned
  helpers only from exact `origin/main`, and ordinary releases never execute
  checkout `ops/*` as root. Launcher alone stops Chromium and cleans namespaces.
- Evidence: affected Go packages and builds — PASS; Dialog 8/8, lint and UI
  build — PASS; four release/bootstrap/security shell suites — PASS.
- One next action: install trusted `fx`/bootstrap on the Factory host, run
  `fx factory install-release-helper <full origin/main commit>`, then release
  `origin/main` and retain the real hung-Chromium cleanup output for Review.

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

### 2026-08-09 — Implement

Повторная реализация закрыла findings остановленного Review: обычный root-owned
release-helper больше не запускает helper или installer из checkout кандидата,
а отдельная операция `fx` принимает только точную вершину `origin/main` и
транзакционно ставит доверенный системный комплект. Go теперь лишь посылает TERM
launcher-группе и ждёт; реальный launcher единолично убивает зависший Chromium и
удаляет namespace. Целевые Go/UI проверки, обе сборки и четыре shell-регрессии
прошли; живая установка доверенного перехода остаётся следующим действием хозяина.

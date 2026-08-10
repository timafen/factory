# CARD-0045 — Серверный браузер в штатном выпуске Factory

## HEAD

- Status: Implemented and targeted checks passed; ready for repeated Review.
- Branch: `factory/d06e6638-8ac-e9d16bcb-121`.
- Head commit: `ea83ba6` (`Дать агентам безопасно видеть стенд серверным браузером`).
- What changed: the exact `origin/main` commit is materialized in a root-owned
  mode-700 staging directory before helpers run; agents and `/dialog` use the
  installed worker path. Browser HTTP checks mutation safety before its slot.
- What changed: the root chain check starts the worker through `runuser` and its
  emergency cleanup terminates tracked process groups and removes every new
  browser namespace.
- Evidence: browser/control-plane/protocol/worker Go checks — PASS; Dialog 8/8,
  lint and production UI build — PASS; four release/security shell suites and
  both Go binary builds — PASS.
- One next action: repeat Review; after merge, Verify runs the live root release
  and browser cleanup through the штатный `fx factory release` path.

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

### 2026-08-09 — Implement

Одним ограниченным проходом закрыты все пять findings Review. Commit кандидата
теперь материализуется и проверяется в недоступном `factory` root-owned staging;
chain-тест запускает установленный worker через `runuser`, использует абсолютный
путь в агентских подсказках, а HTTP-защита срабатывает до browser slot. Аварийный
cleanup завершает отслеживаемые группы и удаляет все созданные namespace. Это
подтверждено целевыми Go/UI/shell-тестами, lint и обеими production-сборками;
живая root-проверка штатным `fx factory release` оставлена этапу Verify после merge.

# CARD-0045 — Серверный браузер в штатном выпуске Factory

## HEAD

- Status: Implemented + targeted tests/build PASS; review blockers closed.
- Branch: `factory/63b342be-244-bcf0e6d5-8e9`.
- Head commit: `ccbeb16` (`Дать агентам безопасный браузер с полным откатом выпуска`).
- What changed: allowlist-прокси слушает только случайный адрес приватного veth;
  CONNECT-туннели имеют дедлайн и гарантированно закрываются вместе с прокси.
- What changed: `fx`, release-helper, browser payload и libexec сохраняются до
  установки и восстанавливаются вместе с бинарями при ошибке либо сигнале.
- Evidence: serverbrowser/worker/API/prompt targeted Go tests — PASS; release
  failure tests и fx browser-sandbox tests — PASS; Dialog UI — 8/8; lint/build — PASS.
- Live evidence: root-проверка недоступна (`sudo -n true` → exit 1).
- One next action: на Factory-host выполнить `fx factory browser-sandbox check`,
  затем открыть `/dialog` и получить снимок утверждённого стенда.

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

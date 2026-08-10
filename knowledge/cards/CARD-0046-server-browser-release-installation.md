# CARD-0046 — Надёжная установка серверного браузера

## HEAD

- Status: Implemented — проверка установки пройдена; ожидает Review.
- Branch: `factory/ef85ac91-7e2-1332354f-a32`.
- Head commit: `c92add7` (`Надёжно установить серверный браузер`).
- What changed: установщик Chromium ставит launcher атомарно, откатывает его при
  неуспешной проверке и находит payload, если сам вызван через симлинк.
- Evidence: `bash ops/test-install-server-browser.sh` — PASS; `bash -n` всех
  четырёх shell-файлов — PASS.
- One next action: Review проверяет трёхточечный diff опубликованной ветки.

## LOG

### 2026-08-10 — Implement

Добавлен доставляемый установщик серверного Chromium, launcher и его проверка.
Регрессия запускает установленную копию через симлинк и подтверждает, что сбой
проверки возвращает прежний launcher-симлинк без изменения его цели.

Проверки `bash ops/test-install-server-browser.sh` и `bash -n` установщика,
launcher, checker и регрессии прошли без ошибок.

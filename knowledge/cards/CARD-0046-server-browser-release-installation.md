# CARD-0046 — Надёжная установка серверного браузера

## HEAD

- Status: Implemented — два блокера закрыты; готово к повторному Review.
- Branch: `factory/3fee0c21-522-298f1580-e20`.
- Head commit: `424e002` (`Выпуск ставит браузер и проверяет запуск через launcher`).
- What changed: штатный выпуск обязательно устанавливает Chromium и прерывается
  при ошибке; Playwright использует установленный launcher и включает sandbox.
- Evidence: обе shell-регрессии — PASS; Vitest 2/2, typecheck, lint, web build и
  `go build ./...` — PASS.
- One next action: Review проверяет связь release → installer → Playwright launcher.

## LOG

### 2026-08-10 — Implement

Добавлен доставляемый установщик серверного Chromium, launcher и его проверка.
Регрессия запускает установленную копию через симлинк и подтверждает, что сбой
проверки возвращает прежний launcher-симлинк без изменения его цели.

Проверки `bash ops/test-install-server-browser.sh` и `bash -n` установщика,
launcher, checker и регрессии прошли без ошибок.

### 2026-08-10 — Implement

Штатный `fx-factory-release` теперь вызывает установщик браузера до замены
серверных бинарей и завершает выпуск с ошибкой, если установка не прошла.
Установочный smoke реально запускает Chromium из Playwright через доставленный
launcher с `chromiumSandbox: true`; ту же связь использует Playwright config.

Shell-регрессии установки и выпуска прошли; Vitest 2/2, typecheck, lint,
production web build и `go build ./...` завершились без ошибок.

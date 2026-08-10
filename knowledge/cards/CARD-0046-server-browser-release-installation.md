# CARD-0046 — Надёжная установка серверного браузера

## HEAD

- Status: Implemented — два блокера закрыты, замечание Review устранено.
- Branch: `factory/2b096285-bc0-93f942e4-23c`.
- Head commit: `058d8dc` (`Выпуск ставит Chromium и проверяет запуск в песочнице`).
- What changed: штатный выпуск обязательно устанавливает Chromium и прерывается
  при ошибке; тест исполняет заглушку `npx` через записанный вызов `sudo` и
  проверяет точные аргументы `playwright install chromium`.
- Evidence: мутация без команды установки — FAIL; shell-регрессии и синтаксис —
  PASS; Vitest 123/123, typecheck, lint, web build и `go build ./...` — PASS.
- One next action: повторный Review проверяет закрытие замечания об установке Chromium.

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

### 2026-08-10 — Implement

Тест установщика теперь записывает вызов `sudo`, исполняет его через
контролируемую заглушку `npx` и явно требует точные аргументы
`playwright install chromium`. Временное удаление команды из установщика
доказанно делает регрессию красной.

Целевые shell-проверки и синтаксис прошли; полный Vitest дал 123/123,
typecheck, lint, production web build и `go build ./...` завершились успешно.

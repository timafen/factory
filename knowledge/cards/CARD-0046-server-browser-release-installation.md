# CARD-0046 — Надёжная установка серверного браузера

## HEAD

- Status: Verified PASS — ожидает человеческого слияния.
- Branch: `factory/2b096285-bc0-93f942e4-23c`.
- Head commit: `ed05554` (`Карточка фиксирует проверку обязательной установки Chromium`).
- What changed: штатный выпуск обязательно устанавливает Chromium и прерывается
  при ошибке; smoke запускает Chromium через launcher без root и с включённой
  Linux-песочницей.
- Evidence: полный чистый прогон: Vitest 60/60, typecheck, lint, production
  build, Playwright E2E, `go test ./...`, `go build ./...` и shell-регрессии — PASS.
- One next action: человек сливает проверенную поставку в `main`.

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

### 2026-08-10 — Verify

| Критерий | Команда/проверка | Наблюдаемый результат |
| --- | --- | --- |
| Chromium обязателен до замены бинарей | `bash ops/test-fx-factory-release.sh` | Установщик идёт после сборок и до сохранения бинарей; его сбой даёт код 5, не перезапускает службы и сохраняет прежние бинарии. |
| Установщик действительно ставит браузер | `bash ops/test-install-server-browser.sh` | Зафиксирован вызов от пользователя Factory: `playwright install chromium`; мутация без этой команды делает регрессию красной. |
| Smoke не ослабляет песочницу | `bash ops/test-install-server-browser.sh`; `npm run test:browser` | Playwright получает установленный launcher с `chromiumSandbox: true`; launcher отказывает root и не содержит флагов отключения песочницы. |
| Смежные проверки поставки | чистый прогон `npm test`, typecheck, lint, build, browser E2E, `go test ./...`, `go build ./...`, shell syntax | Все команды завершились успешно; Vitest: 60/60. |

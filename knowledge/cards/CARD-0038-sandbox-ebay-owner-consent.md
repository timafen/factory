# CARD-0038 — Ключи песочницы: владелец сам даёт согласие eBay

## HEAD

- Status: In progress — Factory готов, включая повтор polling после временного
  сбоя; staging OAuth/callback заблокирован
  зависимостью [`tarser-operations#24`](https://github.com/timafen/tarser-operations/issues/24).
- Branch: `factory/68d22f71-9eb-9f354ab4-c8e`.
- Head commit: `ea110b0` — экран, API, seller bridge и устойчивый polling.
- What changed: `/sandbox-keys` запускает и проверяет согласие без передачи
  секретов; временная ошибка status API теперь запускает ограниченный backoff
  до конечного состояния или ухода со страницы.
- Evidence: shell allowlist, Go, 70/70 UI, TypeScript, build и lint — успешно;
  установленный staging `fx` пока отклоняет `--interactive-bootstrap`.
- One next action: завершить `tarser-operations#24`, штатно установить на
  staging и повторить только живой seller consent smoke.

## LOG

### 2026-08-09 — Implement

По решению владельца polling статуса больше не останавливается после временной
ошибки: запрос автоматически повторяется с backoff не более 12 секунд до
конечного состояния либо ухода со страницы. Новый тест воспроизводит отказ
первого запроса и последующий статус `authorized`; прошли 70/70 целевых UI,
Go, shell allowlist, TypeScript, production build и lint.

### 2026-08-09 — Specification

Проверен код Factory. `ops/fx` уже вызывает staging Django-команду
`bootstrap_sandbox_accounts`, но его allowlist не принимает обязательные
`--interactive-bootstrap --role seller`. Factory не содержит кода eBay, callback
или encrypted token store. Спецификация
`knowledge/specs/sandbox-ebay-owner-consent.md` задаёт минимальную связку:
staging-only allowlist, server-side прокси фиксированной операции, отдельный
экран и polling безопасного статуса. Точный callback/API намеренно оставлен
зависимостью торгового репозитория, чтобы не переносить OAuth в Factory.

### 2026-08-09 — Implement

На ветке `factory/0f6cde34-11f-6563214b-b6d` добавлены экран ключей песочницы,
узкие server start/status endpoints и allowlist только для интерактивного seller
bootstrap на staging. Сервер передаёт UI только operation ID, consent URL, status
и безопасное сообщение; OAuth code, state и токены отсекаются. Проверены
`go test ./internal/controlplane`, `npx vitest run src/SandboxKeys.test.tsx src/App.test.tsx`
и `npx tsc -p tsconfig.app.json --noEmit`.

### 2026-08-09 — Implement

На ветке `factory/cb28ad85-83b-1bb9646b-b94` исправлена зависающая проверка
polling и добавлены сценарии отказа с повторным запуском, остановки polling при
уходе и прямого маршрута `/sandbox-keys`. Целевые 66 Vitest-проверок, Go,
TypeScript, build и lint прошли. Полный Vitest выявил только три прежних сбоя
`Dialog.test.tsx`, не изменённого поставкой; live smoke требует сначала выкатить
новый `fx`.

### 2026-08-09 — Implement

По решению владельца три сбоя полного Vitest воспроизведены на отдельном чистом
снимке свежего `origin/main`: падают ровно те же три теста `Dialog.test.tsx`
(main 98/101, ветка 103/106). Целевые UI-тесты прошли 66/66, отдельная правильная
проверка `npx tsc -p tsconfig.app.json --noEmit`, build, lint и Go-проверки
прошли. Живой smoke остаётся обязательным после обновления `fx` и выката main.

### 2026-08-09 — Implement

По решению владельца реализация из `22a296f` перенесена заново на свежий
`origin/main` без посторонних файлов. Экран, server endpoints, строгий
staging-only seller bridge и тесты закреплены коммитом `dedd492`. Прошли Go,
TypeScript, build, lint и 69/69 целевых UI-тестов; полный Vitest сохранил три
известных сбоя `Dialog.test.tsx`, не затронутого поставкой.

### 2026-08-09 — Implement

По решению владельца реализация и тесты восстановлены на чистой ветке от
свежего `origin/main` коммитом `32bb42a`, без файлов прежней грязной ветки.
Прошли `go test ./internal/controlplane`, 69/69 целевых UI-тестов, TypeScript,
production build, lint и синтаксическая проверка `ops/fx`.

### 2026-08-09 — Implement

На ветке `factory/ec5e0a22-bc4-77e1d145-7ed` реализация заново собрана на
свежем `origin/main`: `/sandbox-keys`, безопасные start/status endpoints и
строгий staging-only seller bridge. Полностью прошли `go test ./...`,
`npm test`, TypeScript, production build и lint; отдельно подтверждены запреты
buyer role и production-вызова. Код реализации закреплён коммитом `0446676`.

### 2026-08-09 — Implement

На ветке `factory/f3c8803b-097-bdc90dfa-e90` поставка заново собрана от
`origin/main` без постороннего `pilot/pilot.py`. Consent allowlist сужен до
точного start и одиночного status ID; отрицательные shell-тесты запрещают
`tenant`, `account`, `force` и пустой ID. Прошли shell, Go, 69/69 UI,
TypeScript, build и lint. Живой start честно не пройден: установленный staging
`fx` ещё не знает `--interactive-bootstrap`, поэтому карточка остаётся в работе.

### 2026-08-09 — Implement

По утверждённому решению владельца реализация снова перенесена только своими
файлами на свежий `origin/main` и закреплена коммитом `f0a327e`. Создана
блокирующая задача
[`tarser-operations#24`](https://github.com/timafen/tarser-operations/issues/24)
на `--interactive-bootstrap`, полный staging OAuth/callback и штатную установку.
Shell allowlist, Go, 69/69 UI, TypeScript, build и lint прошли; живой smoke
отложен ровно до завершения зависимости, production не затрагивался.

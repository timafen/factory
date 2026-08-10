# CARD-0038 — Ключи песочницы: владелец сам даёт согласие eBay

## HEAD

- Status: Verified PASS — ожидает человеческого слияния; Factory-часть уже есть
  в `main`, а staging OAuth/callback по-прежнему заблокирован зависимостью
  [`tarser-operations#24`](https://github.com/timafen/tarser-operations/issues/24).
- Branch: `factory/d658d6d6-9fc-896236a3-6e2`.
- Head commit: current HEAD (verification commit for this card).
- What changed: повторных изменений кода не требуется: `ops/fx` допускает только
  staging seller consent, а controlplane не выдаёт секреты в ответах start/status.
- Evidence: `bash -n ops/fx`, `bash ops/test-fx-sandbox-consent.sh` и
  `go test ./internal/controlplane` завершились успешно 2026-08-10.
- One next action: завершить `tarser-operations#24`, установить bridge на staging
  и повторить живой seller consent smoke.

## LOG

### 2026-08-10 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Владелец сам начинает seller consent и открывает eBay | `just ui-check` | 123/123 UI-теста прошли, включая 8 `SandboxKeys`; eBay открывается только после клика владельца. |
| Ожидание статуса не зависает | `just ui-check` | Тесты `SandboxKeys` подтверждают последовательный polling, повтор после временной ошибки с задержкой не более 12 секунд и остановку при уходе со страницы. |
| Bridge принимает только безопасный staging seller-вызов | `bash -n ops/fx && bash ops/test-fx-sandbox-consent.sh` | Синтаксис корректен; allowlist пропускает только интерактивный seller start или одиночный status ID, подмены отклонены. |
| API не раскрывает OAuth-секреты | `go test ./internal/controlplane` | Успешно; start/status тестируют строгий URL, совпадение operation ID и отсечение токенов, state и URL из status. |

Полный Go-набор `just test` прошёл. `just test-tooling test-launcher` прошёл.
Полный `just check` останавливается только на двух прежних предупреждениях
`staticcheck` в не затронутых карточкой `cards_http.go` и `pilot_config.go`;
после штатного `just ui-install` полный `just ui-check` прошёл 123/123.
Смежный `just test-browser` не прошёл: после одного успешного сценария
`control-plane.spec.ts` завис на выборе отключённого repository в форме
делегирования (120 секунд); остальные 16 browser-сценариев не запускались.
Этот путь не затронут карточкой и не относится к seller consent.
Живой staging smoke не выполнен: он требует завершения `tarser-operations#24`
и установки bridge; production не вызывался.

### 2026-08-10 — Implement

На свежем `origin/main` повторно проверена уже поставленная Factory-реализация:
`ops/fx` принимает только точный интерактивный seller consent на staging, а
controlplane сохраняет узкий безопасный контракт start/status. Повторных правок
кода не вносилось. Успешно прошли `bash -n ops/fx`,
`bash ops/test-fx-sandbox-consent.sh` и `go test ./internal/controlplane`.
Живой smoke остаётся зависимым от `tarser-operations#24` и установки bridge на staging.

### 2026-08-09 — Verify

Проверены экран `/sandbox-keys`, серверный контракт и staging-мост. Владелец
явно открывает URL eBay; UI показывает pending, повторяет временно неудачный
опрос с паузой до 12 секунд и прекращает его после ухода со страницы. HTTP
тесты подтверждают фиксированную seller-операцию и отсутствие URL/секретов в
status; shell-проверка отклоняет все добавочные и подменяющие аргументы.

`go test -timeout 5m ./...`, целевые 70 UI-тестов, tooling и launcher прошли.
Полный UI-набор имеет три несвязанных сбоя `Dialog.test.tsx`; e2e не дошёл до
данного экрана, потому что первый сценарий ожидает устаревший заголовок. Живой
staging smoke заблокирован: установленный `fx` отклоняет `--interactive-bootstrap`.

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

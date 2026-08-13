# Спецификация: экран «Ключи песочницы» — владелец сам даёт согласие eBay

## Goal and user impact

Владелец сможет на экране Factory «Ключи песочницы» запустить согласие
продавца eBay для staging, открыть выданную eBay ссылку в отдельной вкладке и
увидеть итог без передачи OAuth-кода, refresh token или client secret в
Factory. После возврата на `https://staging-automation.tarser.net` токен
сохраняет торговая система в своём существующем зашифрованном хранилище;
Factory отображает только безопасный статус и повторно опрашивает его.

Production в сценарий не входит.

## Текущее поведение и граница задачи

- `ops/fx` уже является единственным root-мостом к staging и сопоставляет
  `fx staging sandbox bootstrap-accounts` с Django-командой
  `bootstrap_sandbox_accounts` в `/srv/automation-ebay-operations/staging`.
  Его allowlist принимает только известные параметры с `=` и не принимает
  `--interactive-bootstrap --role seller`; поэтому утверждённый сценарий
  невозможно безопасно вызвать сегодня.
- `pilot/context.md` явно разделяет `github.com/timafen/factory` и
  `github.com/timafen/tarser-operations`: Factory не содержит Django-кода eBay
  или зашифрованного хранилища токенов.
- `web/src/Access.tsx` — существующий экран общих доступов; это не экран
  OAuth и он не должен получать токены или URL callback. `web/src/App.tsx`
  уже содержит маршрутизацию и пункт «Доступы».
- Точный callback path, параметры eBay и формат безопасного ответа отсутствуют
  в этом репозитории. Их нужно взять из кода и конфигурации
  `tarser-operations`, не читая и не копируя значения секретов.

## Technical approach

Сначала добавить в `tarser-operations` staging-only публичный OAuth callback,
если его ещё нет. Он проверяет `state`, обменивает код с eBay и записывает
результат в уже существующее зашифрованное token store. Callback не обращается
к Factory и не редиректит туда с кодом или токеном.

Затем расширить `ops/fx` ровно одной разрешённой операцией staging для seller:
она запускает существующую Django-команду
`bootstrap-accounts --interactive-bootstrap --role seller`. Она принимает
только этот фиксированный набор аргументов, не принимает произвольные Django
параметры, не доступна в `prod` и возвращает структурированный безопасный
результат: consent URL при старте и конечный статус по идентификатору операции.
Конкретные имена полей, callback path, TTL и terminal states фиксируются после
проверки `tarser-operations`; секреты, OAuth code и access/refresh token в этот
контракт не входят.

Factory добавляет отдельный маршрут `/sandbox-keys`, а не меняет рубильники в
`AccessView`. Небольшой server-side endpoint Factory вызывает только этот
allowlisted `fx` путь, валидирует структурированный ответ и хранит лишь
нечувствительный operation ID/status в памяти или в существующем task-safe
хранилище. UI запускает операцию, открывает URL через пользовательский клик
(`window.open`), показывает «ожидается согласие» и опрашивает status endpoint
до terminal state. Никакой redirect URI Factory, token persistence или eBay
SDK в Factory не добавляется.

### Affected modules/files

- Factory UI: `web/src/App.tsx`, новый `web/src/SandboxKeys.tsx`, его Vitest
  тест; при необходимости — `web/src/api.ts` и `web/src/types.ts`.
- Factory server: новый узкий HTTP handler рядом с
  `internal/controlplane/access_http.go` и его HTTP-тест.
- Root bridge: `ops/fx` и тест/проверка его allowlist.
- Внешняя техническая зависимость: `tarser-operations` — существующая
  `bootstrap-accounts`, публичный staging callback и encrypted token store.
  Файлы этого репозитория будут названы только после проверки его кода и
  конфигурации; их нельзя придумывать или заменять кодом в Factory.

### Data and API changes

Предлагаемый контракт между Factory и `fx` (имена уточняет зависимость):

- `POST /api/v1/sandbox-keys/ebay-seller/consent` запускает одну staging
  операцию и возвращает `{operation_id, consent_url, status:"pending"}`.
- `GET /api/v1/sandbox-keys/ebay-seller/consent/{operation_id}` возвращает
  `{operation_id, status:"pending"|"authorized"|"failed"|"expired",
  message?}`.
- `fx` передаёт JSON только между Factory server и staging Django-командой.
  URL допускается только `https`; Factory не логирует полный URL, `code`,
  `state`, заголовки или токены. Ответ для UI не содержит ничего кроме URL,
  ID, статуса и безопасного сообщения.

Одна активная операция на seller account/tenant предотвращает параллельные
запуски; повторный запрос возвращает тот же pending operation либо
контролируемую ошибку. Источник account/tenant и авторизация владельца должны
использовать уже существующую модель `tarser-operations`, а не доверенный
клиентский параметр из Factory.

## Plan

1. В `tarser-operations` прочитать существующие bootstrap-команду, OAuth
   конфигурацию и encrypted token store; определить callback URL, `state`,
   безопасные terminal states и JSON contract. Если callback отсутствует,
   реализовать и выпустить его на staging до изменений Factory.
2. Добавить staging-only callback и тесты в торговой системе: успешный return,
   отказ пользователя, просроченный/поддельный state и отсутствие утечки
   OAuth-кода/токена в ответе или логах.
3. Изменить `ops/fx`: разрешить только интерактивный seller bootstrap и
   polling статуса, запретить аргументы/production вне контракта; добавить
   проверку allowlist.
4. Добавить Factory server endpoints, которые вызывают только этот `fx` путь,
   нормализуют ошибки и не сохраняют секретные поля; покрыть их HTTP-тестами.
5. Добавить `/sandbox-keys` и пункт навигации в Factory: кнопка запуска,
   открытие согласия по клику, pending/error/success UI и polling с очисткой
   таймера при уходе со страницы.
6. Запустить целевые тесты обоих репозиториев и staging smoke: начать consent,
   пройти eBay в браузере, увидеть `authorized` в Factory и подтвердить, что
   production не вызывался.

## Acceptance criteria

### Согласие владельца

- На `/sandbox-keys` владелец запускает согласие seller eBay и открывает
  выданную ссылку; Factory не требует вручную копировать callback URL.
- Пока eBay не вернул пользователя, экран показывает понятное pending-состояние
  и опрашивает только безопасный статус; после успеха показывает authorized,
  после отказа/ошибки — понятную причину и возможность начать заново.
- URL открывается только по явному действию владельца, а не автоматически в
  фоне или из server-side Factory.

### Изоляция и безопасность

- OAuth callback принадлежит `https://staging-automation.tarser.net`; OAuth
  code и токены не проходят через Factory, её API, БД, browser storage или логи.
- Только фиксированный seller bootstrap разрешён через `fx staging sandbox`;
  произвольные флаги, другой role, `prod` и другие Django-команды отклоняются.
- `state` связывает callback с начатой операцией и не допускает повторное,
  просроченное или поддельное завершение. Токен сохраняется исключительно в
  существующем encrypted store торговой системы.

### Совместимость

- Существующие `bootstrap-accounts`, `seller-policies` и `listings` сохраняют
  прежнее поведение для автоматического сценария песочницы.
- Изменение доступно только на staging; production bridge и production OAuth
  settings не меняются.

## Test plan

- `tarser-operations`: целевые Django tests callback и interactive bootstrap:
  eBay success/cancel/error, `state` validation, encrypted-store write,
  redaction и status transitions.
- Factory bridge: shell/интеграционный тест `ops/fx` допускает только точную
  seller операцию и отклоняет `--role buyer`, произвольный аргумент и любой
  production путь.
- Factory server: Go HTTP tests запуска/status, schema validation, pending
  idempotency и redaction логов/ошибок.
- UI: Vitest для `SandboxKeys`: start, явное открытие URL, polling terminal
  states, отказ и отмена polling при unmount; test маршрута в `App`.
- Команды после реализации: `go test ./internal/controlplane`; `cd web && npx
  vitest run src/SandboxKeys.test.tsx src/App.test.tsx`; `cd web && npx tsc -p
  tsconfig.app.json --noEmit`; целевые тесты `tarser-operations` из его
  существующего test runner. Ручной staging smoke обязателен.

## Risks and decisions requiring approval

1. **Техническая зависимость, блокирует Factory UI.** Callback и JSON contract
   нельзя корректно вывести из данного репозитория. Если callback отсутствует,
   его сначала делает и выкатывает `tarser-operations`; Factory не реализует
   собственный OAuth обходной путь.
2. **Требуется подтвердить контракт после чтения торгового кода.** Нужны точные
   callback path, operation ID, account identity, TTL, terminal status и то,
   где безопасно получить status. До этого нельзя утверждать имена параметров
   или API как окончательные.
3. **Узкий allowlist предпочтительнее общего execute.** Отклонён вариант дать
   Factory произвольную `manage.py`/OAuth команду: он расширяет root-мост и
   делает возможной утечку секретов. Отклонён вариант OAuth в Factory — он
   нарушает утверждённую границу владения токенами.
4. **Не входит в объём.** Подключение buyer/admin roles, production consent,
   редактирование eBay credentials и просмотр token metadata — отдельные
   задачи.

## Card

`knowledge/cards/CARD-0115-sandbox-ebay-owner-consent.md`

## Проверяемые обещания

ГОТОВО-КОГДА: файл `ops/fx`

ГОТОВО-КОГДА: файл `web/src/App.tsx`

ГОТОВО-КОГДА: файл `web/src/SandboxKeys.tsx`

ГОТОВО-КОГДА: файл `internal/controlplane/sandbox_keys_http.go`

ГОТОВО-КОГДА: команда `go test ./internal/controlplane`

ГОТОВО-КОГДА: команда `cd web && npx vitest run src/SandboxKeys.test.tsx src/App.test.tsx`

ГОТОВО-КОГДА: команда `cd web && npx tsc -p tsconfig.app.json --noEmit`

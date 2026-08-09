# CARD-0035 — Зелёная UI-проверка: начальная загрузка экрана «Доступы»

## HEAD

- Status: IMPLEMENTED — исправление и тест восстановлены на свежем `main`,
  обязательные проверки зелёные.
- Branch: `factory/97aa0a90-daf-ee24968d-25d`.
- Head commit: `63e1ace` (коммит реализации; карточка обновлена следом).
- What changed: `web/src/Access.tsx` больше не грузит рубильники через
  `useEffect` + прямой `setState` — читает `useQuery(["access"])`, а
  переключение (`toggle`) после POST рефетчит тот же запрос. Ошибка чтения
  списка по-прежнему видна пользователю. Новый `web/src/Access.test.tsx`
  закрепляет показ загруженного рубильника и повторный GET после переключения.
- Evidence: `cd web && npm test -- --run src/Access.test.tsx` → 2 passed;
  `cd web && npx eslint src/Access.tsx --max-warnings 0` → exit 0;
  `cd web && npx tsc -p tsconfig.app.json --noEmit` → exit 0;
  `cd web && npm run build` → exit 0.
- Next action: влить поставку в `main` после проверки ветки.

## Goal and user impact

Экран «Доступы» продолжает загружать реальные рубильники доступа при открытии и
обновляет их после переключения, но больше не нарушает обязательное правило
React Hooks. Это возвращает один из девяти блокирующих шагов к зелёному
состоянию и уменьшает риск каскадного рендера на экране, с которого владелец
управляет доступами агентов.

## Technical approach

`AccessView` уже работает внутри `QueryClientProvider` (см. `web/src/App.tsx`)
и для других экранов используются `useQuery`/`useMutation`. Начальную загрузку
`GET /api/v1/access`, которая сейчас вызывается из `useEffect` через `load()` и
меняет `scopes`/`err`, нужно перенести в `useQuery` с устойчивым ключом
`["access"]`.

Данные списка будут выводиться из результата query. Сообщение об ошибке чтения
останется видимым так же, как сейчас; ошибка переключения останется отдельным
локальным сообщением. После успешного или неуспешного POST-переключения
`toggle()` обновит query через `refetch` или инвалидацию, вместо вызова
удалённой функции `load`. Маршруты и тела API не меняются:

- `GET /api/v1/access` возвращает `{ scopes?: Scope[] }`;
- `POST /api/v1/access/:key` по-прежнему получает `{ enabled: boolean }`.

Новый `web/src/Access.test.tsx` изолированно замокает `fetch`, отрендерит
`AccessView` под `QueryClientProvider` и закрепит два наблюдаемых сценария:
показ загруженного рубильника и повторный GET после его переключения.

## Plan

1. В `web/src/Access.tsx` заменить локальную начальную загрузку `load()` и
   эффект `useEffect(..., [])` на React Query для `/api/v1/access`.
2. Сохранить текст и состояние ошибок, а `toggle()` привязать к обновлению
   query после POST.
3. Добавить `web/src/Access.test.tsx` для начальной загрузки и переключения.
4. Запустить целевой тест, lint одного файла, затем полный `just ui-check` и
   зафиксировать оставшиеся независимые сбои отдельным следующим срезом.

## Acceptance criteria

1. При открытии «Доступов» успешный `GET /api/v1/access` показывает каждый
   полученный scope с его текущим состоянием.
2. Нажатие «Открыть» или «Закрыть» отправляет тот же POST-контракт и затем
   заново получает список доступов, чтобы UI показывал ответ сервера.
3. `web/src/Access.tsx` не содержит ошибки
   `react-hooks/set-state-in-effect` и проходит ESLint без предупреждений.
4. Обрабатываемая ошибка `GET /api/v1/access` остаётся видимой пользователю.

## Test plan

- Добавить: `web/src/Access.test.tsx` — успешная загрузка и перезагрузка после
  переключения.
- Обязательные команды первого среза:
  - `cd web && npm test -- --run src/Access.test.tsx`
  - `cd web && npx eslint src/Access.tsx --max-warnings 0`
- Контрольная команда: `just ui-check`. До следующих срезов она ожидаемо
  останется красной из-за `Live.tsx`, `Pipeline.tsx`, `Say.tsx` и существующих
  тестов `Overview`, `Settings`, `TaskDetail`, `App`; это не повод расширять
  этот коммит.

## Risks and decisions

- Решение: использовать React Query, а не обходить правило таймером или
  eslint-disable. Так загрузка становится частью единой модели данных UI и
  сохраняет явное повторное чтение после мутации.
- Не включено: восемь других lint-ошибок и четыре test-сбоя. Они относятся к
  другим экранам и должны идти следующими маленькими поставками.
- Риск: формат ошибки Query может отличаться от текущего `String(e)`; тест
  должен закрепить, что пользователь всё равно видит понятное сообщение.

## Card

`knowledge/cards/CARD-0035-ui-access-query-check.md`

## Проверяемые обещания

ГОТОВО-КОГДА: файл web/src/Access.tsx

ГОТОВО-КОГДА: файл web/src/Access.test.tsx

ГОТОВО-КОГДА: команда cd web && npm test -- --run src/Access.test.tsx

ГОТОВО-КОГДА: команда cd web && npx eslint src/Access.tsx --max-warnings 0

## LOG

### 2026-08-08 — Implement

`web/src/Access.tsx` переведён на `useQuery(["access"])`, `toggle()` рефетчит
тот же запрос вместо ручного `load()`. Добавлен `web/src/Access.test.tsx`
(2 сценария). Проверено: `npm test -- --run src/Access.test.tsx` — 2 passed;
`npx eslint src/Access.tsx --max-warnings 0` — чисто, ошибка
`react-hooks/set-state-in-effect` ушла; `npx tsc -p tsconfig.app.json --noEmit`
— чисто. `just ui-check` осознанно остаётся красным: 8 несвязанных
lint-ошибок в других файлах и старые тесты других экранов — следующие срезы.

### 2026-08-09 — Implement

Коммиты реализации и теста восстановлены из истории прежней ветки поверх
свежего `origin/main`. Трёхточечный diff содержит карточку, `Access.tsx` и
`Access.test.tsx`. Проверено: целевые тесты — 2 passed; ESLint, обязательный
`tsc -p tsconfig.app.json --noEmit` и production-сборка — exit 0.

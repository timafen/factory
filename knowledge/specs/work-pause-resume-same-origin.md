# Пауза карточки не показывает внутреннюю same-origin ошибку

## Цель и влияние на владельца

После нажатия «Продолжить» владелец должен сразу видеть, что карточка вышла из паузы и продолжение запланировано. Запрос через живой `https://factory.timafen.com` не должен ошибочно получать `cross_origin_request`; при настоящем отказе владелец видит короткое понятное русское объяснение и безопасную кнопку повтора, а не внутренний английский текст. Завершённая цепочка не должна оставаться в `stopped_owner`.

## Технический подход и реальные файлы

- `internal/controlplane/http.go`: вынести правило валидации Origin в явную проверку web-схем (`http`/`https`) и authority. При прямом запросе сравнивать Origin с `r.Host`; за доверенным loopback-прокси — с одиночными `X-Forwarded-Host` и `X-Forwarded-Proto`. Разрешать смену только схемы при совпадающем authority, не доверять forwarded-заголовкам от внешнего адреса, не принимать пустые/множественные/чужие значения.
- `internal/controlplane/http_test.go`: API security matrix для http и https, прямого и HTTPS-прокси, совпадающего authority; отрицательные случаи для чужого host, схемы, forwarded headers, non-web Origin и непривилегированного proxy.
- `internal/controlplane/work_resume_http.go`: сделать успешное продолжение атомарным с точки зрения наблюдаемого состояния: создать/переиспользовать queued task, затем убрать paused pipeline только после успешной записи; при повторе вернуть тот же task, при ошибке сохранения не терять паузу. Для уже завершённой цепочки вернуть предметный конфликт без stale `stopped_owner`.
- `internal/controlplane/work_resume_http_test.go`: проверить успешный первый resume, idempotent повтор, очистку `StoppedPipelines`, сохранение паузы при ошибке и completed/conflict ветку.
- `web/src/Work.tsx`: после успешного `onResume` очистить локальную ошибку и обновить данные/карточку; отображать только русское безопасное сообщение без `error.message`, технического кода или stack trace. Текст должен объяснять, что продолжение не выполнено, и предлагать повторить; кнопка должна быть доступна после отказа.
- `web/src/Work.test.ts` и `web/src/WorkView.test.tsx`: unit-проверки статуса `stopped_owner`, успешного исчезновения паузы, безопасного русского текста при rejected mutation и сохранения кнопки повтора.
- `web/e2e/control-plane.spec.ts`: внешний сценарий против HTTPS origin через доверенный proxy/живой адрес: открыть Work, продолжить paused card, убедиться в успешном queued/live состоянии и отсутствии `stopped_owner`, `browser mutations must be same-origin` и английского сырого текста; повторить на viewport 390x844.
- `web/playwright.config.ts` (только если нужен конфигурационный режим): добавить opt-in `FACTORY_E2E_BASE_URL`/HTTPS, `ignoreHTTPSErrors` только для тестового сертификата и не менять default local режим; сценарий обязан проверять именно внешний `https://` origin.

## Последовательный план

1. Зафиксировать контракт authority/scheme и security matrix; сохранить запрет доверия к forwarded-заголовкам вне loopback.
2. Исправить resume transaction/idempotency и stale pause cleanup, не изменяя историю задач.
3. Заменить UI-вывод сырой ошибки на русское безопасное сообщение, сбрасывать его при повторной попытке и сразу перечитывать Work/status после успеха.
4. Добавить Go API security и Work unit tests.
5. Добавить внешний HTTPS Playwright flow с отдельным mobile 390px assertion; прогнать целевые тесты и полный diff-gate.

## Критерии приёмки

- Origin `http://authority` и `https://authority` принимается для web-запроса с тем же authority; чужой authority всегда получает 403, независимо от совпадения схемы.
- HTTPS Origin за доверенным loopback-прокси принимается только при одиночных согласованных forwarded host/proto; внешний proxy, расхождение, список значений и non-web scheme отклоняются.
- Успешное продолжение создаёт ровно одну queued задачу или возвращает её при повторе, немедленно убирает паузу, и API/Work больше не показывает `stopped_owner`.
- Если продолжение невозможно, карточка остаётся в паузе, а владелец видит русское объяснение и может безопасно повторить; внутренние английские детали не попадают в DOM.
- Completed pipeline не запускает новый этап и не оставляет ложную остановку.
- Внешний HTTPS сценарий проходит на desktop и viewport 390x844.

## Тест-план

- `go test ./internal/controlplane -run 'TestPrepareMutation|TestResumePausedWork'` — security matrix, idempotency, cleanup и сохранение паузы.
- `npm --prefix web test -- --run src/Work.test.ts src/WorkView.test.tsx` — представление и безопасная ошибка.
- `FACTORY_E2E_BASE_URL=https://factory.timafen.com npm --prefix web run test:browser -- e2e/control-plane.spec.ts` — внешний HTTPS resume flow; при тестовом сертификате использовать только opt-in Playwright setting.
- В E2E явно выставить `page.setViewportSize({ width: 390, height: 844 })` и проверить отсутствие горизонтального overflow, видимость объяснения и кнопки.

## Риски и решения

- Подмена `X-Forwarded-*`: принимать их только от loopback и только парой без запятых; иначе 403.
- Разрешение схемы может ошибочно стать разрешением чужого host: сравнивать нормализованный authority отдельно и обязательно тестировать hostile Origin.
- Скрытие ошибки может замаскировать диагностику: логировать технический код на сервере, но в API/UI отдавать стабильный безопасный текст.
- Гонка повторных кликов может создать дубликат: request key/idempotent lookup под mutex и тест двойного resume.
- Внешний HTTPS E2E может быть недоступен: сделать его явным opt-in gate с ненулевым fail при заданном URL, не подменять проверку локальным HTTP.

## Карточка работы

`knowledge/cards/CARD-0080-work-pause-after-resume-origin-error.md` — единственная карточка этой работы; реализация должна перенести её критерии и evidence в журнал.

## Файлы реализации

`internal/controlplane/http.go`
`internal/controlplane/http_test.go`
`internal/controlplane/work_resume_http.go`
`internal/controlplane/work_resume_http_test.go`
`web/src/Work.tsx`
`web/src/Work.test.ts`
`web/src/WorkView.test.tsx`
`web/e2e/control-plane.spec.ts`
`web/playwright.config.ts` (только при необходимости HTTPS-конфигурации)

ГОТОВО-КОГДА: файл internal/controlplane/http.go
ГОТОВО-КОГДА: файл internal/controlplane/work_resume_http.go
ГОТОВО-КОГДА: файл web/src/Work.tsx
ГОТОВО-КОГДА: файл web/e2e/control-plane.spec.ts
ГОТОВО-КОГДА: команда go test ./internal/controlplane -run 'TestPrepareMutation|TestResumePausedWork'

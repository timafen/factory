# CARD-0080 — пауза карточки после resume и Origin за HTTPS-прокси

## Статус

Specification — READY FOR IMPLEMENTATION. Карточка создана для текущей работы и не заменяет другие CARD.

## Контекст

На живом Factory запрос продолжения идёт через `https://factory.timafen.com`, тогда как browser mutation проходит через control-plane проверку Origin. При сбое карточка сохраняет `stopped_owner`, а UI показывает владельцу сырое внутреннее английское сообщение. Требуется исправить границу безопасности и наблюдаемое состояние, не ослабляя CSRF-защиту.

## Scope

- принять `http` и `https` при совпадающем authority, включая безопасный доверенный loopback proxy;
- отвергать чужой Origin, недоверенный proxy и неоднозначные forwarded headers;
- сделать успешный resume idempotent и немедленно убрать паузу;
- не оставлять completed pipeline в остановленном состоянии;
- показать русское объяснение и безопасный повтор;
- покрыть API security, Work unit, внешний HTTPS Playwright и mobile 390px.

## Реализация и доказательства

Основные файлы: `internal/controlplane/http.go`, `internal/controlplane/http_test.go`, `internal/controlplane/work_resume_http.go`, `internal/controlplane/work_resume_http_test.go`, `web/src/Work.tsx`, `web/src/Work.test.ts`, `web/src/WorkView.test.tsx`, `web/e2e/control-plane.spec.ts`; конфигурация `web/playwright.config.ts` меняется только если без неё невозможно явно прогнать внешний HTTPS.

Обязательное evidence: Go matrix с положительными/отрицательными Origin cases, resume transaction/idempotency tests, unit assertions на отсутствие сырого текста, внешний `https://` Playwright flow с `390x844`, проверяющий исчезновение pause и отсутствие `cross_origin_request` в DOM/API.

## Acceptance

1. Совпадающий authority с любой из web-схем проходит, чужой authority не проходит.
2. Прокси trusted только при loopback source и согласованных одиночных forwarded host/proto.
3. Первый resume создаёт одну queued task и очищает pause; второй возвращает ту же task без дубликата.
4. Ошибка оставляет pause и даёт понятный русский retry; внутренние детали не видны владельцу.
5. Успешная цепочка и completed цепочка корректно отражаются в Work.
6. Desktop и mobile 390px внешний HTTPS сценарии проходят.

## Handoff

Спецификация: `knowledge/specs/work-pause-resume-same-origin.md`.
До реализации не менять UI или исходники приложения на этапе Specification. После реализации приложить команды и результаты из evidence, затем передать карточку на Review.

Implementation commit: f74e4e8b2ae7769fa7fe5edec909044e99da0657 — durable reservation для отвеченной тяжёлой работы, её приоритет и видимое владельцу ожидание.

# CARD-0175 — Возобновление отвеченной HTTPS-проверки

## HEAD

Status: Specification.

Предыдущая реализация reservation существует в истории продолжения работы;
она остановилась на Verify до browser-прогона, потому что committed `web/dist`
отставал от UI-исходников. Эта карточка определяет доведение именно этой
answered HTTPS-проверки: автоматическое resume после 1:48, видимое владельцу
состояние ожидания и запуск реального HTTPS service-worker набора.

## Scope

- Продолжение и идемпотентность answered/resume-pending вопроса в pilot.
- Видимость причины, стадии и давности ожидания на Answer, Work и Overview.
- Синхронная production-сборка `web/dist` и HTTPS Playwright-регрессия с
  активным service worker.

## Acceptance evidence

Новый Chromium-сценарий отвечает на вопрос, моделирует просроченное ожидание
108 минут, показывает владельцу его статус, создаёт одну Verify-стадию и
подтверждает активный `/sw.js` через `navigator.serviceWorker.ready`.

## Handoff

Следующий этап реализует документы из
`knowledge/specs/answered-https-worker-suite-resume-visibility.md`; перед
Verify он обязан пересобрать и закоммитить `web/dist`, поскольку без этого
`just test-browser` корректно не запускает HTTPS-набор.

# CARD-0059 — Полная карточка готовности нового проекта

## HEAD

Implementation commit: e1d50162290f72b3156503a40b0476a36b94df15 — реализована полная карточка готовности проекта из девяти безопасных проверок.

- Status: BLOCKED — встроенный UI-артефакт не соответствует исходникам, поэтому
  сервер не доставит новую карточку без пересборки и фиксации `web/dist`.
- Branch: `factory/e810f198-b10-8f930792-64b`.
- Specification: `knowledge/specs/project-readiness-card.md`.
- What changed: пилот публикует девять упорядоченных проверок, а «Обзор»
  показывает итог, причины и время снимка для каждого enabled-проекта.
- Evidence: Python, целевые Go, Vitest и shell smoke — PASS; полный UI-набор
  (140 тестов) — PASS. После чистого `npm ci` CI-проверка
  `git diff --exit-code -- web/dist` — FAIL: новый bundle не зафиксирован.
- Safe defaults: unknown не становится ready, production-write не требуется,
  rollback не запускается, значения секретов и сырой stderr не публикуются.
- Next action: пересобрать и зафиксировать `web/dist`, затем повторить Verify.

## LOG

### 2026-08-10 — Specification

Зафиксированы существующие источники: каталог/маршрутизация репозиториев в
control plane, провайдерные `fx` probes, политика доступов, release-events и
установочный Chromium smoke. Для отсутствующих durable фактов о Verify и
браузере спецификация требует минимальные allowlisted markers вместо чтения
свободных логов или запуска опасных действий.

### 2026-08-10 — Implement

Реализован снимок готовности из девяти источников, строгая нормализация итогов
в UI и атомарный browser marker после успешного sandbox smoke. Обязательная
составная проверка прошла: 165 Python-тестов, целевые Go-тесты, 20 Vitest,
Playwright-карточка и установочный shell smoke; web build и lint также прошли.

### 2026-08-10 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| 1. Enabled-проект имеет карточку из девяти строк; disabled скрыт | `npm --prefix web test -- --run src/Overview.test.ts` | PASS: 20 тестов, включая девять строк и видимость карточки. |
| 2. Снимок содержит девять ключей и детерминированный итог | `python3 -m unittest pilot.test_pilot`; `go test ./internal/controlplane -run 'PilotConfig|Dashboard|ManagedRepositoryReadiness' -count=1` | PASS. |
| 3. Недоступный факт остаётся unknown с причиной | `pilot.test_pilot`; `Overview.test.ts` | PASS. |
| 4. Вердикты ready/blocked/needs configuration корректны | `pilot.test_pilot`; `Overview.test.ts` | PASS. |
| 5. Нужен только non-production scope, без production-write | `pilot.test_pilot` | PASS. |
| 6. Секреты не публикуются | `pilot.test_pilot` | PASS. |
| 7. Rollback не запускается, событие отделено от процедуры | `pilot.test_pilot` | PASS. |
| 8. Browser ready требует свежий marker после smoke | `bash ops/test-install-server-browser.sh`; `pilot.test_pilot` | PASS. |
| 9. Карточка, итог и причина видимы на «Обзоре» | `npm --prefix web test -- --run src/Overview.test.ts` | PASS. |
| Встроенный UI соответствует исходникам | `npm --prefix web ci && just ui-build 0 && git diff --exit-code -- web/dist` | FAIL: сгенерированы `index-CL1fOjQs.js` и новая ссылка в `index.html`, прежний `index-D63NQG7i.js` удалён. |

Смежные проверки: полный `just ui-check` — PASS (13 файлов, 140 тестов),
`just test-tooling` и `just build` — PASS; `git diff --check origin/main...HEAD`
— PASS. Полный CI-прогон остановлен в `just test-release`; блокирующий CI-шаг
проверки актуальности `web/dist` уже воспроизведён выше.

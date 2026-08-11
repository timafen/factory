# CARD-0059 — Полная карточка готовности нового проекта

## HEAD

Implementation commit: 12098ddce67f0547d3effe57412d5f7017a9865e — реализована полная карточка готовности проекта из девяти безопасных проверок.

- Status: READY FOR VERIFY — реализация и все целевые проверки зелёные;
  известная краснота полного browser-набора относится к смежному Work view.
- Branch: `factory/3dbfae6a-f22-f8c5379b-acf`.
- Specification: `knowledge/specs/project-readiness-card.md`.
- What changed: пилот публикует девять упорядоченных проверок, а «Обзор»
  показывает итог, причины и время снимка для каждого enabled-проекта.
- Evidence: 167 Python-тестов, целевые Go-тесты, 20 Vitest, install-smoke,
  `just build` и отдельный реальный Chromium-сценарий карточки — PASS.
- Safe defaults: unknown не становится ready, production-write не требуется,
  rollback не запускается, значения секретов и сырой stderr не публикуются.
- Next action: на этапе Verify один раз повторить полный набор проверок и
  отдельно учесть уже локализованный внешний сбой Work view.

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

### 2026-08-10 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Встроенный UI соответствует исходникам | `npm --prefix web ci && just ui-build 0 && git diff --exit-code -- web/dist` | PASS: чистая сборка не изменила `web/dist`. |
| Девять строк, итог и причина показаны на «Обзоре» | `just check` | PASS: `Overview.test.ts`, 20 тестов; весь Vitest: 13 файлов, 140 тестов. |
| Снимок из девяти ключей, unknown, безопасные scope/секреты/rollback и browser marker | `just check` | PASS: полный `go test -timeout 5m ./...`, lint, typecheck, tooling и launcher. |
| Релизные артефакты воспроизводимы | `just test-release` | PASS: артефакты, SBOM, checksum и rollback-проверки. |
| Живая карточка в Chromium | `just test-browser` | PASS: `shows project readiness card` (1.6s) на реальном Go server. |
| Полный живой браузерный набор | `just test-browser` | FAIL: 5 passed, 1 failed, 13 did not run; Work view не нашёл `Prove the complete local workflow` в `e2e/control-plane.spec.ts:585`. |

Смежные проверки: `just build` — PASS; `git diff --check origin/main...HEAD` —
PASS; рабочее дерево чисто. Верификация заблокирована до зелёного полного
браузерного набора.

### 2026-08-10 — Implement

Подтверждён реальный implementation-коммит `12098ddce67f0547d3effe57412d5f7017a9865e`
вместо отсутствующего SHA. Девять проверок готовности прошли 167 Python-тестов,
целевые Go-тесты и 20 UI-тестов; install-smoke и сборка — PASS. Отдельный
сценарий карточки прошёл в реальном Chromium: 1 passed. Смежный известный сбой
Work view остаётся за пределами области этой реализации.

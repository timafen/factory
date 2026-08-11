# CARD-0080 — пауза карточки после resume и Origin за HTTPS-прокси

## HEAD

- Status: BLOCKED — полный HTTPS browser suite падает на `route.fetch: self-signed certificate`; runtime-критерии resume/Origin не достигнуты.
- Branch: `factory/154779a5-fa3-d1267776-1f8`
- Implementation commit: 08211c263423a4d563aa56eca9b62f910a0bd240 — timeout 120 секунд установлен первой операцией `beforeAll` и закреплён unit-регрессией.
- What changed: Verify не менял код; проверены review head `04d3f782e37376d5a77c577a8db4c42fd5658703`, чистая сборка и единственный полный browser-запуск.
- Evidence: `FACTORY_BROWSER_LAUNCHER=/missing just check` и отдельный production build прошли; 14 UI-файлов/156 тестов, Go/tooling/launcher PASS, `web/dist` воспроизводим.
- Evidence: `FACTORY_BROWSER_LAUNCHER=/missing just test-browser` собрал 21 тест, но дал `1 passed, 1 failed, 19 did not run`; первый HTTPS page-тест прошёл, второй упал на сертификате в `route.fetch()`.
- Next action: исправить TLS-доверие для Playwright `route.fetch()` без расширения browser trust и вернуть полный 21-test HTTPS suite в Verify.

## LOG

### 2026-08-11 — Implement

- Защищены forwarded host/proto: только loopback, одиночные согласованные web-значения; добавлена точная regression-проверка `127.0.0.1:7337` → body validation 400, не Origin 403.
- Resume очищает pause после принятой queued task и для completed-конфликта; повтор использует ту же задачу, ошибка записи сохраняет pause.
- UI скрывает внутренние API-сообщения и показывает русское объяснение с доступной кнопкой повтора.
- Проверено targeted Go, web unit и production build; внешний HTTPS Playwright не запускался в этой среде.

### 2026-08-11 — Implement

- Добавлен воспроизводимый TLS reverse proxy перед e2e branch build/API: он удаляет supplied `Forwarded`/`X-Forwarded-*` и сам ставит согласованные `X-Forwarded-Host`/`Proto`.
- Новый Playwright fixture создаёт paused и completed pipeline, проверяет HTTPS resume, stale pause cleanup, русский retry и запрет чужого Origin со spoofed forwarding на 1440px и 390px.
- `FACTORY_BROWSER_LAUNCHER=/missing npx playwright test -g 'resumes a paused pipeline through the real HTTPS proxy and keeps Origin protected'` → PASS; snapshots сохранены в `web/test-results/screenshots/pause-resume-https-{desktop,phone}.png`.

### 2026-08-11 — Verify

| Критерий | Команда / проверка | Наблюдаемый результат |
|---|---|---|
| Полные Go/UI проверки, lint и typecheck | `npm ci`; `just check` | PASS: format, vet, vuln, staticcheck, boundary, все Go-пакеты, 14 UI-файлов и 155 тестов, tooling и launcher. |
| Production build воспроизводим | `FACTORY_BUILD_DIR=<tmp>/bin just build`; `git diff --exit-code -- web/dist` | PASS: три Go-бинарника собраны, committed UI dist не изменился. |
| Настоящий HTTPS proxy и очистка spoofed forwarded headers | единственный `just test-browser`, сценарий `resumes a paused pipeline through the real HTTPS proxy and keeps Origin protected` | BLOCKED: Chromium не запущен; сценарий не достигнут. |
| Desktop + 390px resume, stale pause cleanup и безопасный retry | тот же полный browser suite | BLOCKED: первый из 21 тестов упал на `browserType.launch`, 20 не запускались. |
| Нет cross-origin mutations | тот же полный browser suite; полный Go test внутри `just check` | Browser runtime BLOCKED; серверные Go regression-тесты PASS. |
| Нет оставшихся процессов и портов | сравнение `ps -eo pid,ppid,args` и `ss -ltnp` до/после | PASS: новых сокетов и scoped test-процессов нет. |
| Причина блокировки | browser stderr | `/usr/local/libexec/factory/factory-browser-sandbox` вызвал `sudo`; контейнер отклонил его из-за `no new privileges`. |

### 2026-08-11 — Verify

| Критерий | Команда / проверка | Наблюдаемый результат |
|---|---|---|
| Implementation commit стабилен | `git merge-base --is-ancestor 833ec02301b10d7958d4e15aa48133ad7c08f769 HEAD`; `git show --stat 833ec023...` | PASS: commit — предок ветки, не tip карточки и меняет четыре файла вне `knowledge/cards/`. |
| Полные Go/UI проверки, lint и typecheck | `go clean -testcache`; `npm --prefix web ci`; `FACTORY_BROWSER_LAUNCHER=/missing just check` | PASS: format, vet, vuln (`No vulnerabilities found`), staticcheck, boundary, все Go-пакеты, 14 UI-файлов/155 тестов, tooling и launcher. |
| Production build воспроизводим | `FACTORY_BROWSER_LAUNCHER=/missing FACTORY_BUILD_DIR=<tmp>/bin just build`; `git diff --exit-code -- web/dist` | PASS: три Go-бинарника собраны, committed UI dist не изменился. |
| Полный browser suite запускает обычный Chromium | единственный `FACTORY_BROWSER_LAUNCHER=/missing just test-browser` без фильтров | BLOCKED: собрано 21 тест; первый упал, `20 did not run`. Launcher и Chromium стартовали, страница открылась на `https://127.0.0.1:42731/`. |
| Настоящий HTTPS proxy не создаёт browser errors | первый browser-сценарий и сохранённый trace | BLOCKED: регистрация service worker `/sw.js` дала `An SSL certificate error occurred when fetching the script.`, после чего `observeBrowser().assertClean()` упал. |
| Spoofed headers, desktop/390 resume, stale pause, safe retry и cross-origin mutations | целевой serial-сценарий №7 в том же полном suite | BLOCKED: сценарий не запущен из-за падения сценария №1; runtime-доказательства отсутствуют. Серверные Go и UI unit regression-тесты прошли. |
| Cleanup процессов, портов и дерева | `ps -eo pid,ppid,args`, `ss -ltnp`, `git status --short` до/после | PASS: процессов с путём этого worktree и новых listeners нет; tracked/untracked изменений до карточки не было. |

### 2026-08-11 — Implement

- HTTPS fixture теперь создаёт key/cert до старта браузера, переиспользует их между Playwright config/test-worker процессами и передаёт TLS proxy те же paths.
- Chromium получает только `--ignore-certificate-errors-spki-list=<SHA-256 DER SPKI>`; browser-level `ignoreHTTPSErrors` удалён, production и spoofed-header/Origin проверки не менялись.
- `npm --prefix web test -- --run src/playwrightConfig.test.ts`, `typecheck`, `lint`, `just build`, web build и clean `web/dist` → PASS.
- `FACTORY_BROWSER_LAUNCHER=/missing npx playwright test -g 'shows every project product and saves the overview'` → `1 passed`; HTTPS resume/Origin targeted rerun → `1 passed`, без SSL certificate errors.
- Первый холодный запуск resume-сценария упёрся в общий 45-second `beforeAll` timeout; повтор после прогрева прошёл. Полный 21-test suite оставлен Verify по контракту.

### 2026-08-11 — Implement

- `test.setTimeout(120_000)` перенесён в начало общего `beforeAll`, чтобы холодный setup не ограничивался конфигурационными 45 секундами; добавлена unit-регрессия размещения timeout.
- Первый browser-сценарий и HTTPS resume/Origin отдельно прошли с холодным fixture и `FACTORY_BROWSER_LAUNCHER=/missing`: `1 passed (1.0m)` и `1 passed (48.2s)`.
- В обоих логах нет SSL certificate errors; timeout unit (11/11), typecheck, lint, Go/web production build и clean `web/dist` прошли.
- Полный 21-test browser suite оставлен Verify по контракту; открытый риск — только результат этого полного прогона.

### 2026-08-11 — Verify

| Критерий | Команда / проверка | Наблюдаемый результат |
|---|---|---|
| Review head и implementation commit валидны | `git reset --hard FETCH_HEAD`; `git merge-base --is-ancestor 08211c263423a4d563aa56eca9b62f910a0bd240 HEAD`; `git show --stat 08211c263...` | PASS: HEAD до карточки — `04d3f782e37376d5a77c577a8db4c42fd5658703`; implementation — предок, не tip и меняет два code/test-файла вне `knowledge/cards/`. |
| Чистые Go/UI, lint, typecheck и tooling | `go clean -testcache`; `npm --prefix web ci`; `FACTORY_BROWSER_LAUNCHER=/missing just check` | PASS: format, vet, vuln, staticcheck, boundary, все Go-пакеты, 14 UI-файлов/156 тестов, tooling и launcher. |
| Production build и воспроизводимый dist | `FACTORY_BUILD_DIR=<tmp> just build`; browser-команда выполнила `npm run build && git diff --exit-code -- dist`; финальный `git diff --exit-code -- web/dist` | PASS: три Go-бинарника собраны; committed `web/dist` не изменился. |
| Полный HTTPS browser suite ровно один раз | `FACTORY_BROWSER_LAUNCHER=/missing just test-browser` без фильтров и повторов | BLOCKED: собрано 21; первый тест PASS, второй `shows project readiness card` FAIL, 19 не запускались. Ошибка: `route.fetch: self-signed certificate` для `GET https://127.0.0.1:36307/api/v1/dashboard`. |
| Реальный HTTPS, scoped SPKI и service worker | тот же запуск; URL и browser diagnostics | PARTIAL: Chromium со scoped SPKI открыл реальный HTTPS и первый page-тест прошёл без browser SSL errors; activation service worker явно не доказан, suite остановился на отдельном TLS-клиенте `route.fetch()`. |
| Spoofed headers удалены; desktop/390 resume; stale pause; safe retry; cross-origin prevention | serial-сценарий №7 в том же полном suite; Go/UI regressions в `just check` | BLOCKED runtime: сценарий №7 не запущен. Unit/server regressions прошли, но они не заменяют обязательное browser-доказательство. |
| Process, port и tree cleanup | `ps -eo pid,ppid,args` и `ss -ltnp` до/после browser; `git status --short`; `git diff --exit-code -- web/dist` | PASS: scoped процессов и новых listeners нет; до правки карточки дерево и `web/dist` чистые. |

# CARD-0080 — пауза карточки после resume и Origin за HTTPS-прокси

## HEAD

- Status: BLOCKED — обычный Chromium стартовал, но полный Playwright остановился на SSL-ошибке service worker первого сценария; 20 тестов не запустились.
- Branch: `factory/9544acc4-6eb-0c2cd660-356`
- Implementation commit: `833ec02301b10d7958d4e15aa48133ad7c08f769` — настоящий TLS reverse proxy и browser-доказательство resume.
- Evidence summary: после `go clean -testcache` чистый `npm ci`, `just check`, `just build` и `git diff --exit-code -- web/dist` прошли; 14 UI-файлов/155 тестов и все Go-пакеты зелёные.
- Evidence summary: единственный `FACTORY_BROWSER_LAUNCHER=/missing just test-browser` собрал 21 тест и открыл `https://127.0.0.1:42731/`, но первый тест получил `An SSL certificate error occurred when fetching the script.` при регистрации `/sw.js`; `1 failed`, `20 did not run`.
- Cleanup: новых слушающих сокетов и процессов этого worktree после остановки нет; Git-дерево чистое.
- Next action: исправить HTTPS e2e fixture так, чтобы `/sw.js` загружался без certificate console error в обычном Chromium, затем повторить полный 21-test suite.

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

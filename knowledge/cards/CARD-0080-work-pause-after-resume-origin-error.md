# CARD-0080 — пауза карточки после resume и Origin за HTTPS-прокси

## HEAD

- Status: BLOCKED — полный Playwright не запустил Chromium: sandbox launcher требует запрещённый в контейнере `sudo`.
- Branch: `factory/9544acc4-6eb-0c2cd660-356`
- Implementation commit: `833ec02301b10d7958d4e15aa48133ad7c08f769` — настоящий TLS reverse proxy и browser-доказательство resume.
- Evidence summary: чистый `npm ci`, `just check`, `just build` и `git diff --exit-code -- web/dist` прошли; 14 UI-файлов/155 тестов и все Go-пакеты зелёные.
- Evidence summary: единственный `just test-browser` собрал 21 тест, но первый сценарий упал на запуске `/usr/local/libexec/factory/factory-browser-sandbox`; `20 did not run`, поэтому HTTPS/resume/390px/cross-origin runtime-критерии не подтверждены Verify.
- Cleanup: новых слушающих сокетов нет; процессов `e2e/server.mjs`, Playwright/Chromium и тестовых Factory server/worker после остановки нет.
- Next action: повторить полный Verify один раз с `FACTORY_BROWSER_LAUNCHER=/missing` в sandbox, где доступен обычный Playwright Chromium.

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

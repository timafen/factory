# CARD-0043 — Агенты и «Диалог» видят стенд через серверный браузер

## HEAD

- Status: Implemented — целевые проверки и сборка PASS, ожидает Verify.
- Branch: `factory/8c4949df-c81-99c7ff78-cd0`.
- Head commit: `0f84e34` (`Запустить Chromium в ограничениях Ubuntu 24.04`).
- Specification: `knowledge/specs/server-browser-for-agents-and-dialog.md`.
- What changed: общий headless Chromium доступен агентам через
  `factory-worker browser`, а «Диалогу» — через экран и HTTP API.
- Safety: разрешён только `https://staging-automation.tarser.net`; исходные URL,
  переходы, редиректы и разрешённый DNS защищены до сетевого соединения.
- Evidence: CLI получила живой PNG 1440×1000 с approved staging и отклонила
  production до запуска; Go-тесты PASS; UI 6/6, lint, TypeScript и build — PASS.
- One next action: Verify устанавливает Chromium на стенде и открывает `/dialog`.

## LOG

### 2026-08-09 — Specification

Владелец утвердил единственный origin: `https://staging-automation.tarser.net`
с любыми путями. Production, старые стенды, внешний интернет, localhost и
внутренние IP запрещены, в том числе после переходов и редиректов. Выбор
поддерживаемого Chromium и его пути оставлен реализации.

### 2026-08-09 — Implement

Добавлены общий Chromium-runner с закрытым CONNECT-прокси, CLI агента, API и
элемент «Посмотреть стенд» в «Диалоге». Путь браузера определяется явно, через
PATH или по pinned Playwright Chromium; добавлен серверный установщик. Целевые
Go- и UI-тесты, TypeScript и production-сборка прошли.

### 2026-08-09 — Implement (живая проверка)

Pinned Playwright Chromium на Ubuntu 24.04 потребовал `--no-sandbox` из-за
ограничения AppArmor на user namespaces. Браузер остаётся непривилегированным и
сетево закрытым allowlist-прокси. Реальная CLI создала PNG 1440×1000 со страницей
входа approved staging; production URL завершился ошибкой до запуска браузера.

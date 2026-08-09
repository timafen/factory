# CARD-0043 — Агенты и «Диалог» видят стенд через серверный браузер

## HEAD

- Status: Implemented — три замечания Review устранены; ожидает повторный Review.
- Branch: `factory/37c847f9-61d-7557734f-b24`.
- Head commit: `a5b0be5` (`Закрыть браузер песочницей и лимитами сервера`).
- Specification: `knowledge/specs/server-browser-for-agents-and-dialog.md`.
- What changed: Chromium использует штатную sandbox; сетевой фильтр блокирует
  CGNAT и специальные IPv4/IPv6; API ограничен 4 KiB и одним запуском.
- Evidence: целевые Go-тесты PASS; тесты API с race detector PASS; oversized
  request получает 413, занятый browser-slot — 429 до второго запуска.
- One next action: Review проверяет трёхточечный diff опубликованной ветки.

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

### 2026-08-09 — Implement

Недоступная ветка прошлой реализации восстановлена из локальных объектов Git и
перенесена только своими коммитами на свежий `origin/main`. Добавлен проверяемый
запуск Chromium под ограничениями Ubuntu 24.04 и тест CLI-файла с правами 0600.
Живая команда получила PNG 1440×1000 с approved staging; production origin был
отклонён до запуска браузера. Целевые Go/UI-проверки и production-сборка прошли.

### 2026-08-09 — Implement

По решению владельца устранены все три замечания Review: удалён `--no-sandbox`,
CGNAT и специальные IPv4/IPv6 закреплены deny-list и тестами, HTTP API получил
лимит тела 4 KiB и единственный browser-slot. Целевые Go-тесты и тесты API с
race detector прошли; превышение размера возвращает 413, занятый слот — 429.

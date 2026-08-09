# CARD-0043 — Агенты и «Диалог» видят стенд через серверный браузер

## HEAD

- Status: Implemented — целевые проверки, сборка и живая CLI-проверка PASS;
  повторно ожидает Review.
- Branch: `factory/d50664de-35c-f8775f0b-883`.
- Head commit: `3b93f21` (`Проверить приватный снимок из команды браузера`).
- Specification: `knowledge/specs/server-browser-for-agents-and-dialog.md`.
- What changed: общий headless Chromium доступен агентам через
  `factory-worker browser`, а «Диалогу» — через экран и HTTP API.
- Safety: разрешён только `https://staging-automation.tarser.net`; исходные URL,
  переходы, редиректы и разрешённый DNS защищены до сетевого соединения.
- Evidence: CLI получила PNG 1440×1000 с approved staging и отклонила production
  до запуска; целевые Go-тесты PASS; `Dialog.test.tsx` — 6/6 PASS; lint,
  TypeScript, Vite production build и shell-синтаксис установщика — PASS.
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

# CARD-0043 — Агенты и «Диалог» видят стенд через серверный браузер

## HEAD

- Status: Implemented + targeted tests PASS; root environment check pending.
- Branch: `factory/1dbc478d-e98-f2c5e7fb-232`.
- Head commit: will name the implementation commit after the verified commit is created.
- Specification: `knowledge/specs/server-browser-for-agents-and-dialog.md`.
- What changed: Chromium теперь запускается только в отдельном network namespace:
  veth/firewall разрешает ему один TCP endpoint allowlist-прокси; PNG ≤ 4 МБ.
- Evidence: целевые Go-тесты и shell syntax — PASS; root self-check добавлен,
  но живая версия `fx` ещё не содержит `browser-sandbox`.
- One next action: установить новый `fx`, затем выполнить
  `sudo -n fx factory browser-sandbox install` и `check` до Review.

## LOG

### 2026-08-09 — Implement

По решению владельца прокси-флаги заменены обязательной kernel-enforced границей:
root-owned launcher создаёт отдельные network namespace/veth и firewall с одним
разрешённым TCP endpoint. Добавлены `fx factory browser-sandbox install/check`,
root-интеграционная проверка отказа TCP, UDP и DNS и двойной лимит PNG 4 МБ.
Целевые Go-тесты и shell syntax прошли; установленный на хосте `fx` ещё требует
обновления перед живой root-проверкой.

### 2026-08-09 — Implement

После целевого возврата из Review Chromium получил уникальный `--user-data-dir`
в очищаемом временном каталоге. В «Диалоге» capture согласован с send и чтением
локального файла через общий номер операции; два теста воспроизводят одновременные
действия. Целевые Go/UI-тесты, проверка типов и production-сборка прошли.

### 2026-08-09 — Implement

По решению владельца повторён только недостающий контроль: после установки
зависимостей из lock-файла команда `npx tsc -p tsconfig.app.json --noEmit`
завершилась с кодом 0. Трёхточечный diff с `origin/main` содержит ровно 22
заявленных файла серверного браузера, CLI, «Диалога», тестов и документации.

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

### 2026-08-09 — Implement

После блокирующего Review Chromium получил обязательную политику
`disable_non_proxied_udp`, которую закрепляет тест попытки WebRTC-доступа к
внутреннему адресу. CLI теперь атомарно подменяет PNG приватным файлом; тест
начинает с существующего `0644` и подтверждает итоговые права `0600`.

### 2026-08-09 — Implement

Работа заново перенесена на свежий `origin/main` ровно 22 файлами задачи.
После существующих запретов IPv6 теперь допускается только из публичного
`2000::/3`: `fec0::1` и `4000::1` отклоняются, публичный адрес принимается.
Полный Go-набор, 119 UI-тестов, TypeScript, ESLint и production build прошли.

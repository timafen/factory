# CARD-0055 — Идемпотентная установка Chromium при выпуске

Implementation commit: 576455dd14a44b6e24bd05542d6249f5d17c0fa7 — Chromium ставится заново только при изменённом fingerprint или checksum.

## HEAD

- Status: Implemented — ожидает проверки и слияния.
- Branch: `factory/75ab409f-0af-4e76b0ab-c14`.
- Implementation commit: `576455dd14a44b6e24bd05542d6249f5d17c0fa7` — Chromium ставится заново только при изменённом fingerprint или checksum.
- What changed: установщик сохраняет lock-файл, план системных зависимостей, путь и checksum Chromium; неизменный кэш проходит smoke без загрузки. Неоднозначный smoke повторяется и проверяет Factory, сохраняя кэш.
- Evidence: `bash ops/test-install-server-browser.sh` и `bash ops/test-fx-factory-release.sh` — PASS.
- One next action: проверить изменение в обычном выпуске Factory.

## LOG

### 2026-08-10 — Implement

Добавлен fingerprint установленного Chromium и регрессии для повторного выпуска,
неоднозначной недоступности Factory и повреждённого исполняемого файла.
Целевые shell-проверки установщика и сценария выпуска завершились PASS.

# CARD-0055 — Идемпотентная установка Chromium при выпуске

Implementation commit: 3824888720922aee5b3710c05ee8afdbded1bb80 — повреждённый Chromium принудительно загружается заново, а неизменный кэш сохраняется.

## HEAD

- Status: Implemented — ожидает проверки и слияния.
- Branch: `factory/9cf0f65e-e30-9890a063-fcc`.
- Implementation commit: `3824888720922aee5b3710c05ee8afdbded1bb80` — повреждённый Chromium принудительно загружается заново, а неизменный кэш сохраняется.
- What changed: установщик сохраняет fingerprint и пропускает загрузку неизменного Chromium. При несовпадении checksum `--force` обходит `INSTALLATION_COMPLETE`; новый fingerprint записывается после проверки восстановленного бинарника.
- Evidence: `bash ops/test-install-server-browser.sh` и `bash ops/test-fx-factory-release.sh` — PASS.
- One next action: выполнить проверку перед слиянием.

## LOG

### 2026-08-10 — Implement

Добавлен fingerprint установленного Chromium и регрессии для повторного выпуска,
неоднозначной недоступности Factory и повреждённого исполняемого файла.
Целевые shell-проверки установщика и сценария выпуска завершились PASS.

### 2026-08-10 — Implement

Исправлено восстановление повреждённого Chromium: установка при несовпадении
checksum теперь принудительная. Регрессия моделирует `INSTALLATION_COMPLETE`,
повреждает бинарник и подтверждает восстановление файла и исходного fingerprint.
Целевые проверки установщика и выпуска завершились PASS.

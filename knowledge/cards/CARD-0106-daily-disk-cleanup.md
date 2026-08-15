# CARD-0106 — Безопасная ежедневная уборка диска Factory

Implementation commit: eec4fafe35dc2050e713792f71cea76a8409e58a — активные прогоны защищены путём из worker TOML, а janitor получил необходимые ограниченные права.

## HEAD

- Status: Specified from implemented and tested evidence
- Specification: `knowledge/specs/daily-disk-cleanup.md`
- Implementation branch: `factory/cdf7dad9-562-a3089326-7c9`
- What is defined: двухфазная ежедневная уборка старых cache, Playwright,
  quarantine и успешных releases; активные прогоны и аварийные состояния
  защищены fail-closed поведением.
- Acceptance command: `bash -n ops/factory-janitor.sh ops/test-factory-janitor.sh && bash ops/test-factory-janitor.sh`.
- Next action: реализация должна соответствовать спецификации и пройти целевой
  тест перед единственным полным прогоном на Verify.

## LOG

### 2026-08-15 — Specification

Зафиксированы политика хранения, двухфазный манифест, границы разрешённых
каталогов, защита активного worker через `data_directory`, systemd hardening,
критерии приёмки и обязательная целевая проверка.

### 2026-08-12 — Implement

Добавлены двухфазный dry-run/cleanup, fail-closed снимок активных прогонов,
защита выпусков, lock от параллельного запуска и ежедневные systemd units.

### 2026-08-12 — Implement verification

Целевой shell-тест подтвердил восемь сценариев, включая защиту активного пути,
отказ API и ограниченные права systemd service.

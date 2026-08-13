# CARD-0102 — Журнал вливаний пишет круги и участие человека

Implementation commit: 601c3f61b96ffdbe597af0850a650f12b30c80a4 — журнал фиксирует круги и источник вливания до внешнего эффекта

## HEAD

- Status: implemented
- Branch: `factory/b53c0cfc-1b9-74efa853-ce8`
- Implementation commit: `601c3f61b96ffdbe597af0850a650f12b30c80a4`
- What changed: новые merge receipts сохраняют `rounds`, `actor` и nullable `actor_id`; восстановление не меняет атрибуцию.
- What changed: efficiency использует сохранённые круги, а для старых строк сохраняет расчёт по истории задач.
- Evidence: 3 именованных Python-теста — OK; целевой и пакетный `go test ./internal/controlplane` — OK.
- Next action: провести Review реализации и контракта совместимости.

## LOG

### 2026-08-12 — Implement

Реализация добавлена коммитом `601c3f61b96ffdbe597af0850a650f12b30c80a4`.
Автоматическое, человеческое и восстановленное вливания проверены именованными тестами;
новый и legacy-форматы журнала проверены тестом метрики и полным пакетом controlplane.

Implementation commit: c5e63afdd6cecd9a9c208ebae401c9e879f12a33 — спецификация минимального удаления дублирующего gate-копирования

# CARD-0135: тесты Pilot в воротах выпуска

- Status: Specification — ready for implementation
- Scope: убрать второе копирование `ops/test-fx-factory-release.sh` в fixture;
  сохранить реальную проверку `trusted-gate-real-race`.
- Specification: `knowledge/specs/card-0135-remove-duplicate-gate-copy.md`
- Implementation file: `ops/test-fx-factory-release.sh`
- Required verification: `bash ops/test-fx-factory-release.sh` (exit 0)

## Решение владельца

Принят минимальный инженерный вариант: оставить одну подготовку файла перед
сценарием и удалить только второе дублирующее копирование. Ветка
`trusted-gate-real-race` не ослабляется; после реализации обязательна проверка
`bash ops/test-fx-factory-release.sh` с подтверждением реальной гонки.

## Готовность к реализации

В свежей `origin/main` подтверждены две команды копирования одного файла в один
путь на строках 117 и 119 `ops/test-fx-factory-release.sh`. Первая команда
безусловна, вторая находится внутри `trusted-gate-real-race`; поэтому удалить
нужно только вторую. Продуктовый код и UI не входят в область.

## Приёмка

- в fixture остаётся одна команда копирования gate-файла;
- обычные сценарии и `trusted-gate-real-race` сохраняют прежние ветви и
  assertions;
- race-сценарий продолжает противостоять конкурентной подмене доверенного gate;
- `bash ops/test-fx-factory-release.sh` завершается с кодом 0.

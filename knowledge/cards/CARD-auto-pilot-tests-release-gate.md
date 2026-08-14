# Тесты пилота входят в ворота выпуска Factory

Implementation commit: 1dc1b2be9b1c7bee645dda7c961c18cc039ff971 — выпуск Factory останавливается, если полный набор тестов пилота красный.

## HEAD

Status: Implemented — awaiting Review
Branch: factory/4bc02ce1-942-7a07a74e-fa9
Implementation commit: 1dc1b2be9b1c7bee645dda7c961c18cc039ff971 — тесты пилота включены в обязательные release-ворота до сборки и установки.
What changed: release-драйвер запускает `python3 -m unittest pilot.test_pilot` доверенным Python после Go-проверок; красный пилот завершает выпуск с ошибкой до любых мутаций.
Evidence: release-полигон PASS; 268 тестов пилота PASS; полный Go-набор, 180 UI-тестов, lint и production build PASS.
One next action: провести независимый Review опубликованной ветки.

## LOG

### 2026-08-14 — Implement

Ворота выпуска дополнены полным unittest-набором пилота. Отрицательный сценарий
`pilot-test-fail` подтверждает, что после красного пилота не запускаются сценарий
выката, сборка бинарников и установка. Устаревшие тестовые часы и герметичный
снимок Verify обновлены; целевые и полные проверки завершились успешно.

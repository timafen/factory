# Тесты пилота входят в ворота выпуска Factory

Implementation commit: 189c33afc7dcbb438a7377d79d7888946f0c3d52 — выпуск Factory останавливается, если полный набор тестов пилота красный.

## HEAD

Status: BLOCKED: release gate process was killed during signal cleanup
Branch: factory/6fe8f83e-aa4-64f6b776-29f
Implementation commit: 189c33afc7dcbb438a7377d79d7888946f0c3d52 — тесты пилота включены в обязательные release-ворота до сборки и установки.
What changed: release-драйвер запускает `python3 -m unittest pilot.test_pilot` доверенным Python после Go-проверок; красный пилот завершает выпуск с ошибкой до любых мутаций.
Evidence: 268 тестов пилота, полный Go-набор, TypeScript и 180 UI-тестов PASS; полный release-полигон остановлен на `signal TERM`: дочерний процесс получил 137 вместо ожидаемого 130.
One next action: повторить release-полигон в среде без принудительного убийства дочерних процессов и получить Verify PASS.

## LOG

### 2026-08-14 — Implement

Ворота выпуска дополнены полным unittest-набором пилота. Отрицательный сценарий
`pilot-test-fail` подтверждает, что после красного пилота не запускаются сценарий
выката, сборка бинарников и установка. Устаревшие тестовые часы и герметичный
снимок Verify обновлены; целевые и полные проверки завершились успешно.

### 2026-08-14 — Verify

| Проверка | Результат |
|---|---|
| `npx tsc -p tsconfig.app.json --noEmit` | PASS, код 0 |
| `npm test` | PASS, код 0; 180 UI-тестов |
| `go test ./...` | PASS, все пакеты |
| `python3 -m unittest pilot.test_pilot` | PASS, 268 тестов, 13 skipped |
| `bash ops/test-fx-factory-release.sh` | BLOCKED: `signal TERM returned 137 instead of 130`; процесс был убит средой |

Pinned comparison: base `c648f4a4adaa65faefaa6d1806ca1a3090b0afca`, candidate `fbf79d974069828fe99cf7935d02d3a84f088c4b`; изменены только файлы задачи.

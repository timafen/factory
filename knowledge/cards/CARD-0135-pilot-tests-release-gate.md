Implementation commit: a322676d35de33d098dd7faa7976226b4038e986 — полный набор тестов Pilot стал обязательными воротами выпуска

# CARD-0135: тесты Pilot в воротах выпуска

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/715e9393-115-f14ab2b7-b86`
- Implementation commit: `a322676d35de33d098dd7faa7976226b4038e986`
- What changed: `pilot.test_pilot` запускается отдельной параллельной группой до сборки и установки; отказ останавливает соседние ворота.
- What changed: тестовые часы и сценарий доставки Pilot приведены к текущим контрактам полного набора.
- Evidence: чистая проверка `python3 -m unittest pilot.test_pilot` → 264 tests OK, 13 skipped; `bash ops/test-fx-factory-release.sh` → exit 0; `go test -timeout 5m ./...` → exit 0.
- Next action: человеку подтвердить слияние после просмотра доказательств Verify.

## LOG

### 2026-08-13 — Implement

Добавлена доверенная группа «Pilot-проверки» с командой полного unittest-набора.
Shell-фикстура доказала запуск до сборки, публикацию отдельного лога и безопасную
остановку выпуска при ошибке Python. Целевые Python, shell и Go проверки зелёные.

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Pilot обязателен до сборки | `python3 -m unittest pilot.test_pilot` | 264 успешно, 13 пропущено |
| Ошибка Pilot не меняет установку и службы | `bash ops/test-fx-factory-release.sh` | `python-test-fail` оставляет старые бинарники и не перезапускает службы; exit 0 |
| Смежный Go-контур не регрессировал | `go test -timeout 5m ./...` | exit 0 |

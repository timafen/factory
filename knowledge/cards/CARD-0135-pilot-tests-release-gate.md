Implementation commit: a322676d35de33d098dd7faa7976226b4038e986 — полный набор тестов Pilot стал обязательными воротами выпуска

# CARD-0135: тесты Pilot в воротах выпуска

## HEAD

- Status: Implemented and tested — ready for repeated Review
- Branch: `factory/625c1b3c-2d0-bf1205ef-2c1`
- Implementation commit: `a322676d35de33d098dd7faa7976226b4038e986`
- What changed: `pilot.test_pilot` запускается отдельной параллельной группой до сборки и установки; отказ останавливает соседние ворота.
- What changed: тестовые часы и сценарий доставки Pilot приведены к текущим контрактам полного набора.
- Evidence: `python3 -m unittest pilot.test_pilot` → 264 tests OK, 13 skipped; `bash ops/test-fx-factory-release.sh` → exit 0; `bash -n ops/fx-factory-release ops/test-fx-factory-release.sh` → exit 0.
- Next action: повторить независимый Review опубликованного снимка этой ветки.

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

### 2026-08-13 — Implement

Утверждённый владельцем снимок перенесён в новую ветку поставки без изменения
реализации. Повторно пройдены все 264 теста Pilot, герметичный сценарий ворот
выпуска и синтаксическая проверка изменённых shell-скриптов; ветка готова к
повторному независимому Review.

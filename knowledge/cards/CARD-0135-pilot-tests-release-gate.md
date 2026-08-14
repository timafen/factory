Implementation commit: 42fb0b0f54f35bd5e3dc44395c4fa9863a6a27f4 — полный набор тестов Pilot стал обязательными воротами выпуска

# CARD-0135: тесты Pilot в воротах выпуска

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/7b3a1ecf-aa8-544fd174-35e`
- Implementation commit: `42fb0b0f54f35bd5e3dc44395c4fa9863a6a27f4`
- What changed: полный `pilot.test_pilot` запускается отдельной доверенной группой до UI/Go-сборок; его ошибка останавливает выпуск до установки и перезапуска служб.
- Evidence: `python3 -m unittest pilot.test_pilot` → 264 OK, 13 skipped; `bash ops/test-fx-factory-release.sh` → exit 0, включая `python-test-fail`.
- One next action: повторно отправить опубликованную ветку на независимый Review.

## LOG

### 2026-08-13 — Implement

Поставка перебазирована на свежий `main` и опубликована в ветке этого задания.
Повторно подтверждены 264 теста Pilot, герметичный сценарий остановки выпуска
при ошибке Pilot и синтаксис изменённых shell-скриптов.

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

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Pilot обязателен до сборки | `python3 -m unittest pilot.test_pilot`; герметичный успешный релиз | 264 успешно, 13 пропущено; Pilot-ворота записаны до `vite build` и Go-сборок |
| Ошибка Pilot останавливает UI/Go и не трогает установку и службы | `bash ops/test-fx-factory-release.sh` | exit 0; сценарий `python-test-fail` подтверждает остановку обеих соседних групп, отсутствие build/install и перезапуска служб |
| Смежный UI/Go-контур не регрессировал | `just ui-check`; `just test`; `just test-release`; `just test-launcher`; `just vet`; `just staticcheck`; `just boundary` | все команды exit 0 |
| Дерево и карточка пригодны для слияния | pinned `main` → кандидат; `git status` | база `44cc7889f7fd2c81efc8f2b3582f15d0d24e8d63`, кандидат `719e4ecae801fa36016bdf7210c74c95f518bac6`; после проверки дерево чистое |

Полный CI-подобный прогон также зафиксировал две внешние находки: `test-tooling`
в окружении worker сначала получил внешний `FACTORY_BUILD_DIR`, а после его снятия
упёрся в существующий `NoNewPrivileges=false` в unit-файле вне области изменения;
Chromium не устанавливается в контейнере с `no new privileges`. Целевые ворота,
Pilot и Go/UI-проверки от этих ограничений не зависят.

Implementation commit: a322676d35de33d098dd7faa7976226b4038e986 — полный набор тестов Pilot стал обязательными воротами выпуска

# CARD-0135: тесты Pilot в воротах выпуска

## HEAD

- Status: Verified PASS — awaiting human merge
- Branch: `factory/625c1b3c-2d0-bf1205ef-2c1`
- Implementation commit: `a322676d35de33d098dd7faa7976226b4038e986`
- Evidence summary: `python3 -m unittest pilot.test_pilot` → 264 tests OK, 13 skipped; `bash ops/test-fx-factory-release.sh` → exit 0 with Pilot-before-build and no-install/no-service-mutation failure scenarios; UI/Go/release checks → exit 0.
- One next action: человеку проверить опубликованный снимок и слить ветку в `main`.

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

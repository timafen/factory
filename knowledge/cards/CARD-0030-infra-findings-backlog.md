# Infrastructure findings backlog

### 2026-08-09 — Диалог: стабильный идентификатор выбранной модели
Сейчас экран передаёт номер строки `brain_chain`. Если настройки изменятся во
время разговора, номер может указать на другую модель. Передавать имя модели
как стабильный идентификатор, а серверу сверять его с настройками и отклонять
запрос, если такой модели уже нет.

### 2026-08-09 — Диалог: объяснить лимит истории
Сервер ограничивает запрос 40 сообщениями, но экран не объясняет этот лимит
заранее. Добавить заметное объяснение и поведение, которое не создаёт
неожиданный отказ после 20 полных обменов.

### 2026-08-08 — Неатомарный лимит вложений
В `internal/controlplane/attachments.go` проверка числа вложений выполняется
отдельно от создания строки и файла. Одновременные upload с одним `request_key`
могут принять более пяти файлов; лишние blobs затем удалит TTL. Риск принят для
внутреннего однопользовательского инструмента. Рецепт исправления: атомарно
резервировать слот в транзакции и добавить конкурентный тест.

### 2026-08-08 — Экран настроек pilot
На ветке `factory/ddaa8de1-fa2-66c96daa-db5` (проверенный HEAD `b279e48`) добавлены безопасный API и `/settings` для `pilot/config.json`.
Список worker ID впервые берётся из уже известных control-plane исполнителей и дальше хранится в настройках; default остаётся `allow_any_worker=true`.
Доказательство: `go test ./...`, `npm test`, `npm run lint`, `npm run build` (результаты зафиксированы в delivery report).
Открытый риск: pilot не участвует в общем межпроцессном lock; конфликт API определяется по версии непосредственно перед atomic replace.

## HEAD
Status: Verified PASS — ожидает слияния человеком. Branch: `factory/8c403f0f-741-e39c1023-e85`. Head commit: будет указан в завершающем коммите Verify.
What changed: UI-тесты `App.test.tsx` сверены с переименованными экранами и элементами управления; дифф от точки ветвления содержит только этот тест и карточку.
Evidence: после чистого `npm ci` пройдены `npx vitest run src/App.test.tsx` (60/60) и `npx tsc -p tsconfig.app.json --noEmit`; полный `npm test` — 93/94, единственное известное падение в неизменённом `src/Settings.test.tsx` ожидает старый набор `notify_groups` без ключа `escalate`.
One next action: влить ветку в `main`.

## LOG

### 2026-08-08 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Тесты используют новые названия экранов и кнопок | `cd web && npx vitest run src/App.test.tsx` | PASS: 1 файл, 60/60 тестов; проверены «Главное», Workflows, «Показать ещё» и статусы доски. |
| Типы frontend | `cd web && npx tsc -p tsconfig.app.json --noEmit` | PASS: ошибок нет. |
| Смежный полный набор | `cd web && npm test` | Не блокирует поставку: 93/94; единственное падение — неизменённый `src/Settings.test.tsx`, ожидающий `notify_groups` без уже существующего ключа `escalate`. |
| Состав и чистота поставки | `git rebase origin/main`; `git diff --name-only origin/main...HEAD`; `git diff --check origin/main...HEAD` | PASS: после rebase только `web/src/App.test.tsx` и эта карточка, пробельных ошибок нет. |

### 2026-08-08 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Русские названия всех полей и пояснение к каждому | `cd web && npx vitest run src/Settings.test.tsx --reporter=verbose` | PASS: 6/6; специальный тест проходит цикл по всем ~43 полям, проверяя русскую подпись и непустое пояснение. |
| Маршрутизация и уведомления не потеряли настройку | те же Settings-тесты | PASS: проверены таблица маршрутизации, пять групп уведомлений, умолчания и PUT с пятью каноническими ключами. |
| Сборка поставляемого UI | чистый `cd web && npm ci`; `npm run typecheck`; `npm run build` | PASS: TypeScript без ошибок, production-сборка Vite за 5.38 s. |
| Регрессии изменённых файлов | `npx eslint src/Settings.tsx src/Settings.test.tsx`; `git diff --check origin/main...HEAD` | PASS: ESLint без замечаний, пробельных ошибок нет. |
| Полный Vitest | `cd web && npx vitest run --reporter=dot` | Известная база: 79 passed, 15 failed — только неизменённый `src/App.test.tsx`. |
| Полные ESLint и Go tests | `npm run lint`; `go build ./cmd/factory-server && go test ./...` | Известная база: ESLint — 10 ошибок вне диффа (`Access`, `Live`, `Pipeline`, `Say`); Go test не компилирует неизменённый `internal/controlplane/pilot_config_test.go` из-за старого формата `stages`. |
| Browser Settings E2E | `npx playwright test -g 'edits pilot settings from the Settings screen'` | BLOCKED известной базой: API возвращает `pilot config schema is invalid` (старый object-формат `stages` вместо `[]PilotStage`), поэтому экран не загружается до действий сценария. |


### 2026-08-08 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Всегда видны пять групп | `npx vitest run src/Settings.test.tsx` | PASS: найдены все пять русских переключателей |
| Значения берутся из `notify_groups` и умолчаний | тест `uses pilot defaults when notification groups are absent` | PASS: первые четыре включены, `routine` выключена |
| Сохранение сохраняет полный выбор | тест `shows every notification group in Russian and saves the changed selection` | PASS: PUT содержит `questions`, `stuck`, `money`, `done`, `routine` |
| Сборка и типы | `npm run typecheck`; `npm run build`; `go build ./...` | PASS |
| Смежные проверки | `npx vitest run`; `go test ./...`; `npm run test:browser` | 15 старых падений `App.test.tsx`; старый `pilot_config_test.go` не компилирует; Playwright падает на прежнем `Factory overview` до Settings |
| Чистота предметного diff | `git diff --check`; `git diff --name-only 3a055d8...3ff898b` | PASS: семь файлов задачи, без пробельных ошибок |

### 2026-08-08 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Всегда видны пять групп | `npx vitest run src/Settings.test.tsx` | PASS: 5/5; тест находит «Вопросы ко мне», «Работа встала», «Деньги и лимиты», «Завершения и запуски задач», «Рабочая рутина» |
| Значения берутся из `notify_groups` и умолчаний | тот же набор, тест `uses pilot defaults when notification groups are absent` | PASS: первые четыре группы включены, `routine` выключена |
| Сохраняются пять канонических ключей без потери настроек | тот же набор, тест `shows every notification group in Russian and saves the changed selection` | PASS: PUT содержит `questions`, `stuck`, `money`, `done`, `routine`; существующие `_note` сохранены |
| Типы и production build | `npx tsc -p tsconfig.app.json --noEmit`; `npx vite build`; `go build ./...` | PASS |
| Состав и качество диффа | `git diff --name-only origin/main...HEAD`; `git diff --check origin/main...HEAD` | PASS: ровно 8 заявленных файлов, пробелов/маркеров отладки нет |
| Полный Vitest | `npx vitest run` | Известная база: 15 падений только в неизменённом `src/App.test.tsx`; 69 passed, не регрессия поставки |

Смежные общие проверки: `go test ./...` падает на неизменённом `TestHTTPManagedRepositoryCatalog` (404 вместо 200); `npm run lint` — на 11 ошибках вне изменённых файлов; полный и settings Playwright — на прежних ожиданиях экрана/навигации. Эти сбои не затрагивают дифф из восьми файлов и не блокируют merge данной задачи.

### 2026-08-08 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Всегда видны пять групп | `src/Settings.test.tsx`: `shows every notification group in Russian...` | PASS: все пять русских подписей найдены |
| Значения берутся из конфигурации и умолчаний | `src/Settings.test.tsx`: `uses pilot defaults when notification groups are absent`; сверка `/opt/factory-data/pilot/pilot.py` | PASS: `questions`, `stuck`, `money`, `done` включены, `routine` выключен; ключи и умолчания совпадают с пилотом |
| Сохраняется полный канонический выбор | `src/Settings.test.tsx`: `shows every notification group in Russian...` | PASS: PUT содержит пять ключей `notify_groups`, изменён `stuck` |
| Сборка frontend | `npx tsc -p tsconfig.app.json --noEmit`; `npx vite build` | PASS |
| Сборка сервера | `go build ./cmd/factory-server` | PASS |
| Полный набор Vitest | `npx vitest run` | BLOCKED: 69/84, 15 падений только в неизменённом `src/App.test.tsx` (включая устаревший `Factory overview`) |

### 2026-08-08 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Экран Settings показывает конфигурацию | `npx playwright test -g 'edits pilot settings from the Settings screen'` | PASS: открыт `/settings`, видны Pilot settings и Brain chain |
| Изменение сохраняется | тот же Playwright-сценарий | PASS: PUT успешен, `poll_seconds` изменён с 10 на 15 и сохранён после reload |
| Некорректная политика worker отклоняется | `go test ./...` (`TestPilotConfigValidationWorkerPolicy`) и `npm test -- --run` | PASS: строгий неизвестный worker отклонён, UI блокирует сохранение |
| Устаревшая версия не перезаписывает файл | `go test ./...` (`TestPilotConfigStorePreservesNotesAndRejectsConflict`) | PASS: conflict отклонён, содержимое файла не изменено |
| Регрессии смежного UI | `npm run test:browser` | BLOCKED: Workers E2E не нашёл `Implement the modern control-plane UI` на `control-plane.spec.ts:563` |

### 2026-08-08 — Implement

Падение Workers оказалось временной гонкой фикстуры: 30-секундные online-окно worker и lease активной попытки истекали во время последовательного suite. Тест поддерживает lease до своего запуска и посылает свежую регистрацию `Build Mac` перед открытием `/workers`. Полный `npm run test:browser` прошёл: 18/18; Go tests/build и frontend test/lint/typecheck/build также прошли.

### 2026-08-08 — Implement

Поле Configuration note теперь всегда видно и позволяет создать отсутствующий `_note`; регрессионный Vitest проверяет пустое поле и отправку новой заметки. Исправлены фактические branch/HEAD исходной реализации. Доказательство: `go test ./...`, `go build ./...`, `npm test -- --run` (75), `npm run lint`, `npm run typecheck`, `npm run build` и `npm run test:browser` (18) — PASS.

### 2026-08-08 — Implement

В HEAD записан последний содержательный коммит `5d49ada`. Верхний коммит поставки является служебной правкой только этой карточки; при проверке HEAD допустим как родитель вершины ветки. Содержательная реализация и результаты её проверок не изменялись.

### 2026-08-08 — Известные регрессии проверок экрана «Работа»
На ветке `factory/15b971af-c84-e1765036-dbe` предметные Vitest-тесты (7/7), typecheck и production build прошли; релиз `a721b1f` ранее прошёл штатный health-check.
Полный Vitest имеет 15 известных падений в неизменённом `App.test.tsx`, а Playwright ожидает устаревший английский заголовок `Factory overview` вместо «Главное»; по решению владельца они не входят в этап.
Дополнительно текущий `go test ./...` не компилирует неизменённый `internal/controlplane/pilot_config_test.go` из-за рассинхронизации типа `PilotConfig.Stages`; предметный код карточки 0031 это не затрагивает.
Риск: общие наборы останутся красными до отдельных исправлений тестовой инфраструктуры.

### 2026-08-08 — Группы уведомлений на телефон
На ветке `factory/669ce695-1fb-ea64ee84-688` экран Settings получил пять канонических групп и умолчания из pilot.py.
Выбор сохраняется полным `notify_groups`; Vitest Settings 5/5, focused ESLint, typecheck, frontend build и `go build ./...` прошли.
Открытый риск: общие Vitest/lint и `go test ./...` остаются красными на ранее существующих сбоях вне изменённых файлов.

### 2026-08-08 — Чистая поставка групп уведомлений
На ветке `factory/d6cf72b6-b10-192d4077-721` предметный коммит перенесён на свежий `origin/main` без изменений Work, API статуса, навигации и CARD-0031.
Доказательство: Settings Vitest 5/5, typecheck, frontend build, `go build ./...` и `git diff --check origin/main` — PASS.
Открытый риск: полные Vitest/lint и `go test ./...` сохраняют известные сбои в неизменённых файлах базы.

### 2026-08-08 — Implement: доказан старый статус 15 падений Vitest
По решению владельца перед merge требовалось доказать, что 15 падений полного Vitest — не поломка ветки. Установлены зависимости и прогнан `npx vitest run` на чистом `origin/main` (9e46f22, отдельный git worktree в `/tmp/main-check`): та же поставка — Test Files 1 failed | 5 passed, Tests 15 failed | 67 passed, все 15 в неизменённом `src/App.test.tsx`. Список названий упавших тестов на ветке (69/84) и на main (67/82) сверен построчно — совпадает побайтово (разница только в 2 добавленных Settings-тестах). Значит поломка старая, не от этой ветки; merge разрешён без дополнительной починки.
Отдельная задача: завести починку `web/src/App.test.tsx` (15 падений, судя по названиям тестов — устаревшие ожидания после переработки экрана «Работа»/навигации) как самостоятельный тикет вне этого пайплайна.

### 2026-08-08 — Implement: узкая пересборка «русские названия полей и пояснение к каждому»
Предыдущая доставка (`factory/b996395e-1f0-d4c22b55-af4`) вернулась на доработку: Ревью нашло в дифф-е против `origin/main` лишние файлы и слишком выборочный тест пояснений. По решению владельца пересобрано заново от свежего `origin/main` (без rebase/мёржа старой ветки): перенесены только `web/src/Settings.tsx`, `web/src/Settings.test.tsx`, `web/e2e/control-plane.spec.ts`, пересобран `web/dist`. Файлы `internal/controlplane/pilot_config_test.go` и `web/e2e/server.mjs` из старой ветки НЕ перенесены — это несвязанная правка формата `stages` (map → list) в тестовой инфраструктуре, к переводу экрана отношения не имеет; `go vet ./internal/controlplane/...` на чистом `origin/main` уже не собирается по этой же причине — старый известный риск, не входит в эту задачу.
Замечание про тест закрыто: тест `gives every settings field a Russian name and a non-empty explanation` в цикле проверяет все ~43 подписанных поля экрана (aria-label на русском) и наличие непустого `.field-hint` у каждого, плюс отдельно 15 селектов таблицы маршрутизации и оба групповых пояснения.
Доказательство: `npx vitest run src/Settings.test.tsx` (6/6); `npx tsc -p tsconfig.app.json --noEmit`; `npx vite build`; `npx eslint src/Settings.tsx src/Settings.test.tsx`; `go build ./...`; `npx vitest run` — 15 известных падений только в неизменённом `App.test.tsx`, остальное PASS; `git diff --name-only origin/main` — ровно 6 файлов задачи (два — сборка `web/dist`).
Открытый риск: несвязанная поломка `go vet ./internal/controlplane/...` (рассинхронизация `PilotConfig.Stages` map/list в `pilot_config_test.go` и `web/e2e/server.mjs`) остаётся не починенной — уже неоднократно отмечена как отдельная задача вне этого пайплайна.

### 2026-08-08 — Implement: UI-тесты приведены к новым названиям экранов
На ветке `factory/8c403f0f-741-e39c1023-e85` ожидания в `web/src/App.test.tsx` обновлены под актуальные русские названия экранов и элементов управления.
Доказательство: предметный Vitest — 60/60, typecheck и production build — PASS; дифф от точки ветвления содержит только тест и эту обязательную запись.
Отдельная задача: исправить старое ожидание `Settings.test.tsx` для `escalate: true` и 10 существующих lint-ошибок, включая `Say.tsx`; эти сбои не блокируют текущую поставку по решению владельца.

### 2026-08-10 — Диагностичные паузы эффективности Factory
На ветке `factory/0b497be3-b54-7e0be31f-cd0` коммит `c042aff96f99ca9a9d781d131c84b1db80a77c40` разложил время по доказанным ожиданиям между стадиями, решения владельца, слияния и `unclassified`.
API и Обзор показывают определения, секунды, доли, число интервалов и красный сигнал при `unclassified > 20%`; product по-прежнему отделён от patrol/scheduled/helper.
Доказательство: `go test -timeout 5m ./...`, `go vet ./...`, 131 Vitest и 145 Python-тестов, ESLint, typecheck, `npm run build`, `go build ./...` — PASS.
Открытый риск: старые вопросы без `asked_at`/`answered_at` намеренно остаются `unclassified`; новые записи получают обе метки.
### 2026-08-10 — Закрытая работа не оживает из истории
На ветке `factory/7e663adc-1d8-a3ec917d-ad2` Pilot получил общий барьер закрытия и поколения во всех путях продолжения; причина и старые закрытия сохраняются, а явный повтор создаёт новое поколение.
Implementation commit: 2a25b03edd0b35d7f905896dc3bfba72f538531f — закрытые, архивные, заменённые и завершённые в Плане работы не продолжаются из старых terminal-задач.
Доказательство: `python3 -m unittest pilot.test_pilot` — 151/151; `go test -timeout 5m ./...` и `go build ./...` — PASS.
Открытый риск: внешний создатель без карточки распознаётся как явный повтор только по новой live-задаче, созданной строго после durable close.
### 2026-08-10 — Ускорение штатного Factory release
На ветке `factory/cd375a22-ad7-7e63b68a-83e` UI-проверки и группа Go + shell-регрессии запускаются параллельно в отдельных сессиях; установка ждёт оба успешных результата.
Раздельные полные журналы выводятся после ожидания; отказ или HUP/TERM завершает и дожидается обеих групп без фоновых помощников.
Доказательство: `bash ops/test-fx-factory-release.sh`, чистый `npm ci` + typecheck/test/Vite и `go test ./...` — PASS.
Открытый риск: привилегированный живой выкат намеренно не запускался; его процессная семантика покрыта изолированной shell-фикстурой.

### 2026-08-10 — Загрузка четырёх потоков на Обзоре
На ветке `factory/6ab50efb-d7c-6f0f66e4-296` добавлены durable samples product works: 24ч/7д, 0–4 активных, средняя занятость, p90 очереди и причины простоя.
Доказательство: `go test ./internal/controlplane` и `npm --prefix web test -- --run src/Overview.test.ts` проходят; production build веба проходит.
Риск: до накопления как минимум двух сэмплов API и UI честно показывают low data; незафиксированные причины очереди остаются `unknown`.

### 2026-08-10 — Implement: метрика потоков не зависит от открытого Обзора
На ветке `factory/ea9c8aa0-f66-6ecfe85f-26f` коммит `5837b6fb789c0eed095a17758952882ade88cc10` считает direct/delegated product tasks и пишет durable samples серверным минутным sampler; patrol, Automation и служебные префиксы исключает общий с efficiency классификатор.
Доказательство: `go test -count=1 ./...`, targeted `go test -race`, 132/132 Vitest, `go vet ./...`, ESLint, `go build ./...` и web production build — PASS; тест sampler получил два сэмпла без GET и подтвердил shutdown.
Открытый риск: точные причины `provider_limit`, `repository_conflict` и `release_lock` появятся только после добавления отдельного durable/system источника; пока недоказанная блокировка честно остаётся `unknown`.

### 2026-08-10 — Остановленный выпуск не оставляет тестовые процессы
На ветке `factory/0724b7f5-761-f2293c84-560` очистка ждёт готовность pid-файла process group, затем завершает и дожидается обеих тестовых групп при ошибке, HUP, INT, TERM и EXIT.
Фоновая оболочка явно сбрасывает наследованный ignored SIGINT до запуска тестов; параллельные ворота сохранены.
Доказательство: `bash -n ops/fx-factory-release && bash -n ops/test-fx-factory-release.sh` и `bash ops/test-fx-factory-release.sh` — PASS; HUP/INT/TERM повторены по 5 раз, `/proc` и `ps` не нашли cmdline/cwd фикстур.
Открытый риск: привилегированный живой выкат не запускался; семантика процессов покрыта изолированной фикстурой и live-проверкой `ps` после неё.

### 2026-08-14 — Implement: Pilot доигрывает завершения после рестарта
На ветке `factory/1adc0ddd-022-8b955a6b-6aa` Pilot сохраняет watermark и startup-набор, восстанавливает только свежий отсутствующий хвост и защищает handoff от дублей.
Доказательство: 13 целевых restart/terminal-проверок, обязательный тест, `py_compile`, `git diff --check` и `just build` — PASS.
Открытый риск: полный набор `pilot.test_pilot` и live-стенд не запускались на этапе Implement + Test; живой API не менялся.

### 2026-08-15 — Implement: очистка осиротевших каталогов выпуска
На ветке `factory/7ae0b62e-58b-16ce3093-377` коммит `496b6a3a6682133b4d5c3e804a334466977d7c21` перед сборкой удаляет реальные верхнеуровневые временные каталоги вне `generations/`, независимо от префикса.
Ссылки, включая `current`/`previous` и внешние цели, не затрагиваются; история поколений сохраняется.
Доказательство: `bash ops/test-fx-factory-release.sh` и `just check` — PASS, включая скрытый каталог, альтернативный префикс и внешнюю symlink.
Открытый риск: живой выкат не запускался, поскольку изменение покрыто изолированной регрессионной фикстурой и не меняет интерфейс продукта.

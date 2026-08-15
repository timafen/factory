Implementation commit: ab728815799fae74056647c6fb58e309ee2784f4 — production-сборка синхронизирована с текущим Vite, чтобы browser-набор не останавливался до Playwright.

# CARD-0093 — Резервирование отвеченной тяжёлой работы

## HEAD

Status: PASS — полный HTTPS-набор завершён с реальным service worker.
Branch: `factory/0f7281c4-7b4-33a9182d-427`.
Implementation commit: ab728815799fae74056647c6fb58e309ee2784f4 — production-сборка синхронизирована с текущим Vite, чтобы browser-набор не останавливался до Playwright.
What changed: `web/dist` теперь соответствует текущему `npm run build`; барьер `git diff --exit-code -- dist` пройден.
What changed: сценарий после возобновления показывает владельцу «Ожидает слияния и выпуска», а не ложное финальное завершение.
Evidence: `FACTORY_BROWSER_LAUNCHER=/usr/local/libexec/factory/factory-browser-sandbox just test-browser` — PASS, 23/23 за 5,7 мин; HTTPS resume/Origin-сценарий пройден.
One next action: проверить и влить ветку.

## LOG

### 2026-08-12 — Specification

Владелец утвердил политику: после ответа резервировать ближайший слот именно
для уже разблокированной тяжёлой стадии, не запускать до неё новые тяжёлые
автоматические работы и не прерывать выполняющиеся. Спецификация отделяет
admission от `no_worker`, требует durable reason в question и видимость на
Answer, Work и Overview.

### 2026-08-12 — Implement

- `pilot` записывает reservation в отвеченный вопрос, восстанавливает его после
  рестарта, отдаёт ему первый допустимый слот и не даёт новой тяжёлой автозадаче
  обойти его; memory/disk emergency остаётся запретом запуска.
- `no_worker` теперь означает только отсутствие совместимого worker; dashboard
  и все требуемые экраны показывают принятое решение и честную причину ожидания.
- Целевой Python-профиль: 7 PASS; Answer/Work/Overview: 29 PASS; typecheck,
  lint и production build PASS. В базовом `Work.tsx` восстановлен обрезанный
  блок WorkView, без которого экран не компилировался.

### 2026-08-12 — Rebase

Код перебазирован на актуальный `main`; конфликт `Work.tsx` решён поверх
целого актуального компонента с сохранением только статуса reservation.
Повторные целевые Python- и UI-проверки после rebase прошли: 7 и 29 тестов.

### 2026-08-12 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Reservation сохраняется, переживает рестарт, получает первый слот без дубля | `python3 -m unittest pilot.test_pilot.AnswerEscalationTests` | PASS, 7/7; профиль также покрывает блокировку новых тяжёлых задач, лёгкую стадию, emergency и честный `no_worker` |
| Answer, Overview и Work видны владельцу без нового вопроса и badge | `npx vitest run src/Answer.test.tsx src/Overview.test.ts src/WorkView.test.tsx` | PASS, 29/29 |
| Типы и production-сборки | `npx tsc -p tsconfig.app.json --noEmit`; `npx vite build`; `go build ./cmd/factory-server` | PASS |
| Полный локальный набор | `just check` | FAIL только в неизменённом `internal/worker/TestLostClaimAndCompletionResponsesAreIdempotent`; отдельный повтор теста PASS за 3.629s, классифицирован как внешний флейк |
| HTTPS/browser-набор с реальным service worker | `just test-browser` | BLOCKED до Playwright: committed `web/dist` расходится с результатом сборки |
| Область и чистота | pinned diff `b448350413748b951462b5db8e999b59d7f8e278...618bd7f0cff780dc8f1aaf24757c379a1cece9bc`; `git status --short` | 11 заявленных файлов до Verify-карточки; дерево чистое после удаления проверочных артефактов |

### 2026-08-15 — Implement

- Зафиксирована обновлённая production-сборка `web/dist`: полный HTTPS/browser-набор преодолел прежний build-barrier и запустил Chromium с реальным service worker.
- Единственное падение полного прогона было в устаревшем тексте ожидания: после принятой проверки продукт корректно показывает ожидание слияния и выпуска. Сценарий обновлён и целевой HTTPS Playwright прошёл: 1 PASS за 55,5 с.

### 2026-08-15 — Implement

- После явного требования владельца повторён полный `just test-browser`. Первый запуск выявил и подтвердил рассинхронизацию committed `web/dist` с текущим Vite; production-артефакты синхронизированы в `ab728815799fae74056647c6fb58e309ee2784f4`.
- Повторный запуск прошёл build и проверку чистоты `dist`, затем запустил Playwright. Среда оборвала процесс без финальной сводки; журнал `/tmp/card-0093-test-browser-final.log` содержит независимый `daily_report_failed`: отсутствует абсолютный `FACTORY_BROWSER_LAUNCHER`.

### 2026-08-15 — Implement

- Диагностика подтвердила рабочий изолированный Chromium launcher `/usr/local/libexec/factory/factory-browser-sandbox` для пользователя `factory`; Playwright Chromium установлен в кэше.
- Полный `FACTORY_BROWSER_LAUNCHER=/usr/local/libexec/factory/factory-browser-sandbox just test-browser` завершился: 23/23 PASS за 5,7 мин. Включая реальный HTTPS resume/Origin-сценарий, который использует service worker.

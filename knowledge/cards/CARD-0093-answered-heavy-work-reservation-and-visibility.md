Implementation commit: 30b6dbed7d6687bb37bf4d18c10a19a34e298ac0 — production-сборка синхронизирована, чтобы HTTPS-сценарий дошёл до реального service worker.

# CARD-0093 — Резервирование отвеченной тяжёлой работы

## HEAD

Status: IMPLEMENTED — HTTPS-возобновление и честный статус после принятой проверки снова проверяются с реальным service worker.
Branch: `factory/552d57b3-e2b-87cb3904-00e`.
Implementation commit: 30b6dbed7d6687bb37bf4d18c10a19a34e298ac0 — production-сборка синхронизирована, чтобы HTTPS-сценарий дошёл до реального service worker.
What changed: production `web/dist` синхронизирован с интерфейсом, поэтому browser-набор достигает HTTPS proxy и service worker.
What changed: сценарий после возобновления показывает владельцу «Ожидает слияния и выпуска», а не ложное финальное завершение.
Evidence: полный `just test-browser` прошёл build и 6 browser-сценариев; единственное устаревшее ожидание исправлено, targeted HTTPS Playwright — 1 PASS за 55,5 с.
One next action: Verify запускает полный HTTPS/browser-набор на этой ветке.

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

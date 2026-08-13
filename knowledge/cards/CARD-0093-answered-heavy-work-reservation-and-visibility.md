Implementation commit: f74e4e8b2ae7769fa7fe5edec909044e99da0657 — отвеченная тяжёлая работа получает durable reservation, ближайший допустимый слот и видимое объяснение ожидания.

# CARD-0093 — Резервирование отвеченной тяжёлой работы

## HEAD

Status: BLOCKED — committed `web/dist` не соответствует изменённому UI, поэтому HTTPS/browser-набор не доходит до запуска с реальным service worker.
Branch: `factory/78a1871e-f1e-08ec2a95-2a7`.
Implementation commit: f74e4e8b2ae7769fa7fe5edec909044e99da0657 — отвеченная тяжёлая работа получает durable reservation, ближайший допустимый слот и видимое объяснение ожидания.
What changed: reservation хранится в записи вопроса, восстанавливается после рестарта и пропускает к ближайшему допустимому слоту только отвеченную тяжёлую стадию.
What changed: dashboard, Answer, Work, Overview и навигация показывают «ответ принят», но не выдают новый badge и не требуют нового решения владельца.
Evidence: reservation-поведение PASS — Python 7/7 и UI 29/29; `tsc`, Vite и Go build PASS. `just test-browser` → FAIL на проверке committed `web/dist`: сборка заменяет `index-Dzu-Lcbr.js` на `index-COKb8iDy.js`, поэтому HTTPS/Playwright не запускается.
One next action: пересобрать и закоммитить `web/dist`, затем вернуть ветку на Verify полного HTTPS/browser-набора.

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

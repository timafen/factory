Implementation commit: f74e4e8b2ae7769fa7fe5edec909044e99da0657 — отвеченная тяжёлая работа получает durable reservation, ближайший допустимый слот и видимое объяснение ожидания.

# CARD-0093 — Резервирование отвеченной тяжёлой работы

## HEAD

Status: Implemented — awaiting Review.
Branch: `factory/78a1871e-f1e-08ec2a95-2a7`.
Implementation commit: f74e4e8b2ae7769fa7fe5edec909044e99da0657 — отвеченная тяжёлая работа получает durable reservation, ближайший допустимый слот и видимое объяснение ожидания.
What changed: reservation хранится в записи вопроса, восстанавливается после рестарта и пропускает к ближайшему допустимому слоту только отвеченную тяжёлую стадию.
What changed: dashboard, Answer, Work, Overview и навигация показывают «ответ принят», но не выдают новый badge и не требуют нового решения владельца.
Evidence: `python3 -m unittest pilot.test_pilot.AnswerEscalationTests` → PASS, 7 tests; UI reservation tests → PASS, 29 tests; typecheck, lint и `just build` → PASS.
One next action: провести Review и Verify полного набора.

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

# Спецификация: ежедневный PDF-отчёт с честным сравнением «до/после»

## Цель и влияние на владельца

Каждое утро владелец получает в Factory готовый PDF за предыдущий календарный
день: понятную инфографику по результатам конвейера, сравнение операционных
метрик с предшествующим днём и пары снимков изменённых экранов. Для визуальной
работы больше нельзя полагаться на догадку агента: при постановке явно задаются
URL, проверяемое состояние страницы и viewport. Снимок «до» делается до допуска
агента к работе, а «после» — в тех же неизменяемых условиях.

Если «до» получить не удалось или эта функция включена уже после начала работы,
PDF прямо показывает «Снимок до отсутствует» и сохранённую причину. Случайный
эталон, экран «Обзор» или снимок другой работы никогда не используются. «Обзор»
разрешён только как явно выбранный URL работы, которая меняет именно его.

## Технический подход и реальные файлы

### Данные и API

- `migrations/029_daily_visual_reports.sql` добавляет `task_visual_targets`
  (root task, URL, обязательный видимый текст состояния, width/height и момент
  финального capture), `visual_captures` (phase `before|after`, status,
  sha256/path/time/error) и `daily_reports` (локальная дата, timezone, status,
  metrics JSON, PDF path/hash/error). Уникальные ключи `(work_id, phase)` и
  `(report_date, timezone)` делают повтор запуска идемпотентным.
- `internal/protocol/types.go` и `web/src/types.ts` получают `VisualTarget`,
  `VisualCapture` и `DailyReport`. `visual_target` в `CreateTaskRequest` означает
  визуальную работу; сервер принимает его только целиком: абсолютный HTTPS URL
  (HTTP допустим лишь для loopback), непустой точный текст, который должен быть
  виден, viewport 320..2560 × 320..2560 и `after_workflow_title`. Для ручной
  работы последнее поле пусто; для auto UI отправляет `Verify`.
- `internal/controlplane/store.go` валидирует и атомарно сохраняет target вместе
  с root task. Дочерние задачи наследуют его через уже существующие
  `parent_task_id`/`work_id`; переданный дочерним запросом другой target
  отклоняется. Это не требует дублировать визуальные поля в `pilot/pilot.py`.
- `internal/controlplane/reports_http.go` и регистрация маршрутов в
  `internal/controlplane/http.go` дают `GET /api/v1/reports/daily` и
  `GET /api/v1/reports/daily/{date}/pdf`. Незавершённый или отсутствующий файл
  не отдаётся как PDF; download использует сохранённые размер/hash и безопасный
  basename.

### Захват и ежедневная сборка

- `internal/controlplane/reports.go` реализует очередь capture/report и интерфейс
  renderer. Пока `before` имеет `pending|running`, `internal/controlplane/claiming.go`
  не выдаёт root task воркеру. Ошибка capture переводится в `missing` с причиной
  и снимает блокировку: работа продолжается, но отсутствие остаётся фактом.
- `internal/controlplane/state.go` ставит `after` после успешного завершения
  ручной root task либо задачи с Workflow, равным неизменяемому
  `after_workflow_title`. Ошибка/отмена финальной стадии оставляет `after`
  отсутствующим с объяснением и не создаёт ложную пару.
- `web/report/capture.mjs` использует уже установленный Playwright и
  `FACTORY_BROWSER_LAUNCHER`: открывает только сохранённый URL, выставляет
  viewport, ждёт точный видимый текст состояния и пишет PNG атомарно. Обе фазы
  используют один target; редирект на login, timeout, несовпавший текст и
  browser/network error дают `missing`, а не снимок другой страницы.
- `web/report/render.mjs` получает от Go нормализованный JSON, строит локальный
  HTML с inline CSS/SVG-инфографикой и печатает его через Chromium `page.pdf`.
  Внешние ресурсы и URL при рендере запрещены. PDF содержит период/timezone,
  завершённые/успешные/неуспешные работы, медианное время цикла, first-pass
  Review/Verify и дельты «предыдущий день → отчётный день» из существующих
  запросов `metrics.go`/`efficiency.go`, затем карточки визуальных работ.
- PDF и PNG лежат отдельно от входных `task_attachments` в
  `/opt/factory-data/reports`; `internal/controlplane/store.go` создаёт каталог
  с mode 0700. Отчёт строится один раз после окончания календарного дня в
  явно настроенной timezone, а после рестарта безопасно продолжает pending job.
  `cmd/factory-server/main.go` запускает и останавливает runner вместе с сервером.
- `ops/install-server-browser.sh` устанавливает report scripts и pinned Node
  runtime рядом с уже проверяемым Playwright, а `ops/fx-factory-release`
  включает scripts в атомарный release/rollback inventory. Их shell-тесты
  доказывают, что новая версия не зависит от временного release checkout и при
  неуспешном выпуске возвращается тем же комплектом, что server binary.

### Интерфейс

- `web/src/DelegateModal.tsx` добавляет флаг «Меняется видимый экран». При нём
  обязательны URL, точный видимый текст состояния, ширина и высота; auto mode
  фиксирует финал на `Verify`. Ошибки показываются до отправки.
- `web/src/Reports.tsx`, `web/src/App.tsx`, `web/src/api.ts` и
  `web/src/styles.css` добавляют русскоязычный экран «Отчёты»: дата и timezone,
  статус, основные дельты, число полных/неполных пар и скачивание готового PDF.
  На карточке незавершённого отчёта видна причина, а не неработающая ссылка.

## Последовательный план

1. Добавить миграцию, protocol-типы, валидацию target, наследование по `work_id`
   и store-тесты несовместимых/неполных условий.
2. Реализовать durable capture queue и claim gate; fake renderer-тестом доказать,
   что агент не стартует раньше terminal `before`, а ошибка сохраняется как
   `missing` и не блокирует работу навсегда.
3. Подключить sandboxed Playwright capture; проверить одинаковый URL/state/
   viewport, login redirect, timeout и атомарную запись артефакта.
4. Включить report scripts и pinned runtime в browser install и атомарный
   self-release, проверив install/rollback shell fixtures.
5. Добавить постановку `after` на правильной финальной стадии, суточный срез
   метрик и идемпотентный report runner с восстановлением после рестарта.
6. Реализовать HTML/SVG → PDF renderer без внешних запросов и HTTP list/download;
   отдельно проверить честный placeholder при отсутствующем `before`.
7. Добавить поля постановки и экран отчётов, unit-тесты и один Playwright-сценарий
   от создания visual task до скачивания валидного PDF.

## Критерии приёмки

- Визуальную задачу нельзя создать с частичным target; auto task хранит URL,
  видимый state marker, viewport и `Verify` как финал. Обычные невизуальные и
  существующие scheduled tasks продолжают работать без target.
- Первый claim визуальной root task невозможен до terminal-результата `before`.
  Успешный снимок имеет PNG content, hash и условия capture; отказ имеет статус
  `missing`, человекочитаемую причину и не заменяется иным изображением.
- `after` снимается ровно один раз после успешной целевой стадии в тех же URL,
  state и viewport. Повтор completion/restart не создаёт вторую пару.
- На каждый завершившийся календарный день существует не более одного PDF для
  timezone. Повтор генерации возвращает тот же durable record; повреждённый или
  неполный файл не помечается `ready`.
- PDF открывается стандартным reader, содержит подпись периода, инфографику и
  метрики двух соседних дней с выборкой/`нет данных`, а для каждой visual work —
  название, условия, «до/после» либо явный missing-placeholder с причиной.
- Экран «Отчёты» не показывает машинные статусы/голые ID владельцу и позволяет
  скачать только `ready` PDF. Экран «Обзор» не выбирается неявно ни в одном пути.

## Тест-план

- `go test ./internal/controlplane -run 'TestVisualTarget|TestDailyVisualReport'`
  — валидация, inheritance, claim gate, idempotency, метрики и честные пропуски.
- `node --test web/report/*.test.mjs` — sandbox options, одинаковые условия двух
  captures, login/error handling, отсутствие внешних запросов и PDF signature.
- `npm --prefix web test -- --run src/DelegateModal.test.tsx src/Reports.test.tsx src/App.test.tsx`
  и `npm --prefix web run typecheck` — обязательные поля, русские статусы и route.
- `npm --prefix web run test:browser -- --grep "creates an honest daily visual PDF report"`
  — visual task, обе фазы, missing-before fixture и скачивание `%PDF-`.
- На Verify один раз выполнить полный `go test ./...` и полный web suite.

## Риски и решения

- Произвольное интерактивное состояние нельзя надёжно воспроизвести из прозы.
  Поэтому MVP трактует state как точный видимый текст после открытия URL; modal,
  login/setup или последовательность кликов требуют отдельного расширения, а не
  скрытой эвристики.
- У Factory уже есть Chromium, но нет runtime PDF-кода. Используем его pinned
  Playwright и sandbox launcher, не вводя второй browser/PDF stack; installer
  обязан оставить `web/report` рядом с установленным `web/package.json`.
- Операционные метрики Factory не равны бизнес-KPI целевого продукта. PDF честно
  называет их метриками конвейера; извлечение чисел со страницы или сторонние KPI
  не входят в эту работу.
- Скриншоты могут содержать персональные данные. Каталог закрыт mode 0700,
  endpoint доступен через существующую авторизацию Factory, внешние URL при PDF
  render запрещены; автоматическая очистка не вводится до отдельного решения о
  сроке хранения.
- Отчёт за день может появиться позже из-за временной ошибки Chromium. Runner
  хранит `pending/error`, повторяет с ограниченной задержкой и никогда не
  публикует частичный файл как готовый.

## Карточка работы

`knowledge/cards/CARD-0155-daily-visual-report-pdf.md`

ГОТОВО-КОГДА: файл migrations/029_daily_visual_reports.sql
ГОТОВО-КОГДА: файл internal/protocol/types.go
ГОТОВО-КОГДА: файл internal/controlplane/store.go
ГОТОВО-КОГДА: файл internal/controlplane/claiming.go
ГОТОВО-КОГДА: файл internal/controlplane/state.go
ГОТОВО-КОГДА: файл internal/controlplane/reports.go
ГОТОВО-КОГДА: файл internal/controlplane/reports_http.go
ГОТОВО-КОГДА: файл internal/controlplane/reports_test.go
ГОТОВО-КОГДА: файл internal/controlplane/http.go
ГОТОВО-КОГДА: файл cmd/factory-server/main.go
ГОТОВО-КОГДА: файл web/report/capture.mjs
ГОТОВО-КОГДА: файл web/report/render.mjs
ГОТОВО-КОГДА: файл web/report/report.test.mjs
ГОТОВО-КОГДА: файл ops/install-server-browser.sh
ГОТОВО-КОГДА: файл ops/test-install-server-browser.sh
ГОТОВО-КОГДА: файл ops/fx-factory-release
ГОТОВО-КОГДА: файл ops/test-fx-factory-release.sh
ГОТОВО-КОГДА: файл web/src/DelegateModal.tsx
ГОТОВО-КОГДА: файл web/src/DelegateModal.test.tsx
ГОТОВО-КОГДА: файл web/src/Reports.tsx
ГОТОВО-КОГДА: файл web/src/Reports.test.tsx
ГОТОВО-КОГДА: файл web/src/App.tsx
ГОТОВО-КОГДА: файл web/src/App.test.tsx
ГОТОВО-КОГДА: файл web/src/api.ts
ГОТОВО-КОГДА: файл web/src/types.ts
ГОТОВО-КОГДА: файл web/src/styles.css
ГОТОВО-КОГДА: файл web/e2e/control-plane.spec.ts
ГОТОВО-КОГДА: команда sh -c "grep -q 'func TestDailyVisualReportKeepsMissingBeforeHonest' internal/controlplane/reports_test.go && go test ./internal/controlplane -run '^TestDailyVisualReportKeepsMissingBeforeHonest$'"

# CARD-0045 — Аудит переноса сторожа и автоматизаций Fable

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/6b7a512d-d08-5490389d-893`.
- Head commit: `cf7c17e` (фактически проверенная поставка контракта завершения аудита).
- Specification: `knowledge/specs/fable-automation-migration-audit.md`.
- What changed: в спецификации закреплены точный файл поставки и обязательная
  команда проверки автономного сторожа.
- Evidence: полный Go-набор, 87 проверок `pilot` и 121 web-проверка прошли;
  целевые `PipelineWatchTests` (7 сценариев) и Go-сценарии автоматизаций — OK.
- Limitation: абсолютный исторический паритет с Fable без её исходников не доказан и не заявляется.
- One next action: человеку влить поставку в `main`.

## LOG

### 2026-08-09 — Implement

Проверка завершена по утверждённой владельцем матрице: автономный сторож,
GitHub issue/PR, cron, восстановление после рестарта и операторские HTTP API
присутствуют в Factory. Сторож прошёл 7 целевых сценариев, Go-набор
автоматизаций прошёл. Недоступность Fable зафиксирована как ограничение
исторической полноты, а не как блокировка текущего аудита.

### 2026-08-09 — Implement

Исправлена метаданная карточки: версия проверенного снимка приведена к
фактически поставленной ревизии. Матрица, доказательства и ограничение
исторической полноты Fable не менялись; целевые проверки повторяются перед
сдачей.

### 2026-08-10 — Verify

| Проверяемый критерий | Команда или проверка | Наблюдаемый результат |
| --- | --- | --- |
| Матрица связывает известные механизмы с реализацией и тестами | чтение `knowledge/specs/fable-automation-migration-audit.md` | все шесть механизмов имеют путь реализации и именованный тест |
| Сторож не требует сети или второго процесса | `python3 -m unittest pilot.test_pilot.PipelineWatchTests` | 7 сценариев OK |
| Issue/PR, cron, restart и operator API | `go test ./internal/controlplane -run 'Test(Automation|PullRequestAutomation|HTTPAutomation|ScheduleAutomation)' -count=1` | пакет OK |
| Смежные регрессии | `go test ./... -count=1`; `python3 -m unittest pilot.test_pilot`; `npm run lint`; `npm run build` | Go и Python OK; lint и production build OK |
| Ограничение вывода | проверка формулировок решения и остаточных пробелов матрицы | исторический паритет без исходников Fable не заявлен; их отсутствие не блокирует аудит |

Полный `npm test` обнаружил один тайм-аут `Settings.test.tsx` (5 секунд).
Это существующая web-проверка вне двух файлов поставки и вне области Fable;
целевая проверка поставки, lint и production build успешны.

### 2026-08-10 — Implement

В спецификации закреплено машинно-проверяемое завершение аудита: наличие
самого файла поставки и успешный запуск `PipelineWatchTests`. Все 7 сценариев
сторожа прошли; ограничение исторического паритета с недоступной Fable
сохранено без расширения объёма реализации.

### 2026-08-10 — Implement

HEAD карточки приведён к фактически проверенной поставке `cf7c17e` и текущей
рабочей ветке. Остальные метаданные сверены с поставкой; повторный review не
обнаружил расхождений в области, доказательствах и заявленном ограничении.

### 2026-08-10 — Verify

| Проверяемый критерий | Команда или проверка | Наблюдаемый результат |
| --- | --- | --- |
| Матрица связывает шесть известных механизмов с Factory и тестами | проверка `knowledge/specs/fable-automation-migration-audit.md` | у каждого механизма есть путь реализации и именованные автоматические сценарии |
| Сторож автономен | `python3 -m unittest pilot.test_pilot.PipelineWatchTests` | 7 сценариев OK без сети и второго процесса |
| Issue/PR, cron, рестарт и operator API | `go test ./internal/controlplane -run 'Test(Automation|PullRequestAutomation|HTTPAutomation|ScheduleAutomation)' -count=1` | пакет OK |
| Полный набор проекта | `go test ./... -count=1`; `python3 -m unittest pilot.test_pilot -v`; web: `npm run lint && npm run typecheck && npm test && npm run build` | Go OK; 87 Python-проверок OK; lint/typecheck, 121 UI-тест и production build OK |
| Граница вывода | сверка решения и остаточных пробелов в спецификации | исторический паритет с недоступным исходником Fable не заявлен |

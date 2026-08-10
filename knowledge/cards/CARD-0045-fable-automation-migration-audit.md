# CARD-0045 — Аудит переноса сторожа и автоматизаций Fable

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/d8291cc8-15a-a9a49bc3-521`.
- Head commit: `fca900a` (проверенный снимок матрицы аудита после перебазирования на `main`).
- Specification: `knowledge/specs/fable-automation-migration-audit.md`.
- What changed: утверждённая владельцем матрица стала окончательным объёмом аудита; все известные и доступные механизмы сопоставлены с реализацией Factory и тестами.
- Evidence: `PipelineWatchTests` → 7 tests OK; целевые Go-тесты автоматизаций → OK; полный Go- и Python-наборы → OK.
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

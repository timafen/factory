# CARD-0127 — Замок областей не создаёт взаимного ожидания

Implementation commit: f20b23139066bf8fe43278259e2a4d5ddf73202c — арбитр разводит живые работы с пересекающимися областями

## HEAD

- Статус: Implemented — ready for review.
- Ветка: `factory/aa802da6-3ae-d50e791d-f56`.
- Implementation commit: f20b23139066bf8fe43278259e2a4d5ddf73202c — арбитр выбирает одного устойчивого владельца полной пересекающейся области и разводит оба production-пути.
- What changed: арбитр сортирует живые работы по стабильному приоритету, сравнивает repository/path и выдаёт одному владельцу всю область; `area_busy` и `review_gate` используют единое решение.
- Evidence: `python3 -m unittest -v pilot.test_pilot.AreaLockArbitrationTests` — 7 тестов OK; `python3 -m py_compile pilot/pilot.py` — OK.
- Следующее действие: Проверить опубликованный кандидат на review.

## LOG

### 2026-08-13 — Implement

Работа заново собрана от свежего `origin/main`; перенесены только `pilot/pilot.py`,
`pilot/test_pilot.py` и эта карточка. Кодовый коммит f20b23139066bf8fe43278259e2a4d5ddf73202c
прошёл 7 целевых тестов и компиляцию Python; арбитраж учитывает полную область,
repository/path, стабильный приоритет и не даёт завершённой работе обойти живого владельца.

### 2026-08-13 — Implement

Первый сосед больше не выбирается по порядку ответа `/tasks`: арбитр сортирует
всех живых кандидатов, допускает только непересекающиеся полные области и
возвращает ожидающему устойчивого владельца. Регрессии подтверждают порядок,
ручной tie-break, отсутствие частичного захвата и изоляцию repository/path.

### 2026-08-13 — Implement

Оба production-вызова теперь передают арбитру UUID и полную запись текущей
работы, поэтому её плановый приоритет не теряется. Регрессии через `area_busy`
и `review_gate` воспроизводят две живые пересекающиеся работы: первая проходит,
вторая ждёт первую, взаимного ожидания нет. Целевые 6 тестов и `py_compile` прошли.

### 2026-08-13 — Verify

| Критерий | Команда / проверка | Наблюдение |
| --- | --- | --- |
| Стабильный владелец в обоих production-путях | `python3 -m unittest -v pilot.test_pilot.AreaLockArbitrationTests` | 6 тестов, OK; `area_busy` пропускает первого владельца, `review_gate` ждёт его для второй работы. |
| Сборка и полный Go-набор без регрессий | `go build ./...`; `go test -timeout 5m ./...` | Сборка OK; все Go-пакеты OK, включая controlplane и worker. |
| Полный Python-набор и отделение проектного долга | `python3 -m unittest -v pilot.test_pilot`; тот же проблемный тест на pinned base | 260 тестов, 13 skipped, 2 известных падения; оба падения повторились на base. |
| Карточка и реализация закреплены корректно | pinned bare-проверки ancestry и изменённых путей | Implementation commit — предок candidate и меняет `pilot/pilot.py` и `pilot/test_pilot.py`; рабочее дерево проверяющего чистое. |

### 2026-08-13 — Verify

| Критерий | Команда / проверка | Наблюдение |
| --- | --- | --- |
| Арбитраж разводит две живые работы над одним файлом | `python3 -m unittest -v pilot.test_pilot.AreaLockArbitrationTests` | Все 7 тестов OK: один владелец проходит, второй ждёт; порядок входных данных не меняет победителя, область не захватывается частично. |
| Кандидат, уже завершившийся, не обходит живого владельца | `AreaLockArbitrationTests.test_finished_candidate_does_not_bypass_live_owner` | Тест OK: `succeeded`-кандидат не получает пересекающуюся область вместо `running`-владельца. |
| Регрессии соседнего поведения проверены полным набором | `python3 -m unittest -v pilot.test_pilot` | 261 тест, 13 skipped; 2 падения в `CorrectionProvenanceStormTests` воспроизведены на pinned base и не относятся к изменённым файлам. |
| Код собирается и дерево чистое | `python3 -m py_compile pilot/pilot.py`; `git status --short` | Компиляция OK; до изменения карточки рабочее дерево было чистым, stray/debug-файлов нет. |

### 2026-08-13 — Implement

Ветка восстановлена из опубликованной прошлой работы и остаётся основанной на свежем
`origin/main`; итоговый diff содержит только `pilot/pilot.py`, `pilot/test_pilot.py`
и эту карточку. Целевые 6 регрессий, `py_compile` и сборка Go прошли; два Python-
падения повторены на pinned base, а падение worker остаётся вне области задачи.

### 2026-08-13 — Implement

Завершённая работа больше не считается живым кандидатом арбитра, поэтому не
обходит `running` или `queued` владельца пересекающейся области. Добавлена
регрессия `succeeded` кандидата против действующего владельца: целевые 7 тестов
и `py_compile` прошли.

### 2026-08-13 — Implement

Работа заново собрана от свежего `origin/main`; кодовый коммит содержит только
`pilot/pilot.py` и `pilot/test_pilot.py`. Арбитр стабильно выбирает одного
владельца полной области, а оба production-пути ждут его; 7 целевых тестов,
`py_compile` и `go build ./...` прошли.

### 2026-08-13 — Verify

| Критерий | Команда / проверка | Наблюдение |
| --- | --- | --- |
| Две живые работы над одним файлом получают одного владельца | `python3 -m unittest -v pilot.test_pilot.AreaLockArbitrationTests` | 7/7 OK: `area_busy` пропускает одного владельца, `review_gate` ждёт его для второй работы; порядок ответа, tie-break, целостность области и границы repository/path проверены. |
| Завершённый кандидат не обходит живого владельца | `AreaLockArbitrationTests.test_finished_candidate_does_not_bypass_live_owner` | OK: `succeeded`-кандидат отклонён, владельцем остаётся живая работа. |
| Полный набор и соседняя сборка | `go build ./...`; `go test -timeout 5m ./...`; `python3 -m py_compile pilot/pilot.py`; `python3 -m unittest -v pilot.test_pilot` | Go build OK; все Go-пакеты OK; Python compile OK; полный Python-набор: 261 тест, 13 skipped, 2 известных падения. |
| Известные падения не внесены кандидатом | Тот же `CorrectionProvenanceStormTests.test_review_and_verify_corrections_complete_one_pipeline_after_restart` на pinned base | На базе воспроизведены те же 2 падения; они вне изменённого арбитража. |
| Кандидат и карточка закреплены | `git ls-remote --symref origin HEAD`; pinned bare fetch; `base_sha...candidate_sha`; проверка ancestry и diff путей | База и кандидат закреплены; implementation commit — предок кандидата и меняет код; diff содержит только карточку, `pilot/pilot.py`, `pilot/test_pilot.py`; временный снимок чистый. |

### 2026-08-13 — Implement

Работа перенесена в текущую ветку `factory/aa802da6-3ae-d50e791d-f56`; карточка
теперь ссылается на реальный кодовый коммит f20b23139066bf8fe43278259e2a4d5ddf73202c.
Арбитраж подтверждён 7 целевыми тестами и компиляцией `pilot/pilot.py`.

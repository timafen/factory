# CARD-0044 — Выкат проверяет один настоящий ответ мозга

## HEAD

- Status: Verified PASS — ожидает слияния человеком.
- Branch: `factory/df988a93-8ca-42199f72-094`.
- Head commit: `5f8f748` (проверенная поставка).
- Specification: `knowledge/specs/factory-brain-release-smoke.md`.
- What changed: установщик задаёт один контрольный вопрос через `/suggest-answer`;
  при изменении `pilot/` перезапускает также импортирующий его `factory-intake`
  перед smoke и повторно перезапускает обе службы после отката.
- Evidence: целевой smoke и регрессия выкладки → PASS; `pilot/test_pilot.py` —
  65 тестов OK. Полный `just check` остановился только на двух прежних замечаниях
  staticcheck вне поставки.
- Decision: smoke проходит новый загруженный код через реальный `/suggest-answer`.
- One next action: человек проверяет результаты и принимает решение о слиянии.

## LOG

### 2026-08-09 — Specification

Текущий `ops/install-brain.sh` после замены файлов проверяет активность служб и
`GET /health`, но не способность `pilot.brain` ответить. Действующий
`POST /suggest-answer` в `intake/app.py` уже проводит запрос через полный модельный
путь и возвращает объект с `answer`; спецификация использует этот контракт без
изменения API. Отказ smoke-проверки включается в существующий возврат `.prev` и
перезапуск затронутых служб. Общая атомарность с ранее установленными server/worker
явно оставлена вне области.

### 2026-08-09 — Implement

`ops/install-brain.sh` теперь делает ровно один POST к `/suggest-answer` после
готовности служб и принимает только объект с единственным непустым строковым полем
`answer`. Ошибка транспорта, HTTP, JSON или формы ответа включает прежний откат;
быстрый путь без изменений не расходует модельный вызов. `bash
ops/test-install-brain.sh`, синтаксическая проверка и существующая регрессия общего
выката завершились PASS.

### 2026-08-09 — Implement

После замечания Review pilot-only выкладка перезапускает `factory-intake`, чтобы
smoke проверял свежий импорт `pilot.py`; при откате intake также перезапускается с
возвращённым файлом. Отдельная регрессия изменяет только `pilot.py` и фиксирует
порядок обоих перезапусков вокруг единственного smoke-запроса. `bash
ops/test-install-brain.sh`, синтаксическая проверка и интеграционная регрессия
`bash ops/test-fx-factory-release.sh` завершились PASS.

### 2026-08-09 — Verify

| Проверка | Команда | Результат |
| --- | --- | --- |
| Один вопрос и единственный непустой ответ | `bash ops/test-install-brain.sh` | PASS; успешный путь делает один POST |
| Откат ошибочного ответа | `bash ops/test-install-brain.sh` | PASS; timeout, HTTP, JSON, пустой и лишнее поле возвращают файлы и перезапускают службы |
| Путь модели и контракт endpoint | `python3 -m unittest pilot/test_pilot.py` | 65 тестов, OK |
| Соседний общий выкат | `bash ops/test-fx-factory-release.sh` | PASS |
| Синтаксис установщика | `bash -n ops/install-brain.sh ops/test-install-brain.sh` | PASS |

Полный `just check` прошёл format, vet и проверку уязвимостей, но остановился на
двух существующих ошибках staticcheck: неиспользуемом поле `err` в
`internal/controlplane/cards_http.go` и присваивании в
`internal/controlplane/pilot_config.go`. Эти файлы не входят в поставку; целевые
проверки релиза прошли.

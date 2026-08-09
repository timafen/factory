# CARD-0044 — Выкат проверяет один настоящий ответ мозга

## HEAD

- Status: Implemented — замечание Review исправлено, ожидает повторный Review.
- Branch: `factory/db8a319e-58b-9e3593fb-88c`.
- Head commit: `9527fd2`.
- Specification: `knowledge/specs/factory-brain-release-smoke.md`.
- What changed: установщик задаёт один контрольный вопрос через `/suggest-answer`;
  при изменении `pilot/` перезапускает также импортирующий его `factory-intake`
  перед smoke и повторно перезапускает обе службы после отката.
- Evidence: `bash ops/test-install-brain.sh` → PASS; `bash
  ops/test-fx-factory-release.sh` → PASS; `bash -n ops/install-brain.sh
  ops/test-install-brain.sh` → PASS.
- Decision: smoke проходит новый загруженный код через реальный `/suggest-answer`.
- One next action: провести повторный Review исправления pilot-only выкладки.

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

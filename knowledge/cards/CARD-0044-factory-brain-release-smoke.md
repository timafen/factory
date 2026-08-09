# CARD-0044 — Выкат проверяет один настоящий ответ мозга

## HEAD

- Status: Implemented — целевая регрессия зелёная, ожидает Verify.
- Branch: `factory/da9711b7-be2-cf7f1e98-157`.
- Head commit: `931f9c3`.
- Specification: `knowledge/specs/factory-brain-release-smoke.md`.
- What changed: установщик после обновления задаёт один контрольный вопрос через
  `/suggest-answer`; только строгий непустой JSON-ответ подтверждает новый мозг.
- Evidence: `bash ops/test-install-brain.sh` → PASS; `bash
  ops/test-fx-factory-release.sh` → PASS; `bash -n ops/install-brain.sh
  ops/test-install-brain.sh` → PASS.
- Decision: smoke проходит реальный `/suggest-answer` и модель, а не только `/health`.
- One next action: на Verify повторить целевую регрессию и один полный набор проверок.

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

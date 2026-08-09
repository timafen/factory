# CARD-0034 — Мозг конвейера переключается после лимита подписки

## HEAD

- Status: BLOCKED: целевая проверка зелёная, но полный UI-набор содержит
  четыре падения вне диффа этой работы.
- Branch: `factory/14902703-a11-c9268e6a-7b6`.
- Head commit: `ce2f6b3` (повторная проверка переключения подписок).
- What changed: `pilot.brain()` теперь передаёт `conf` в `note_limit()` при
  срабатывании rate-limit, поэтому блок реально сохраняется в `limits.json`.
  Добавлен тест `BrainFallbackTest`, который сначала бьёт исчерпанного Codex
  во втором вызове `brain()` (красный без фикса), затем подтверждает, что он
  больше не запускается, пока Claude отвечает сразу.
- Evidence: после перебазирования `python3 -m unittest pilot.test_pilot` → OK
  (2 теста), `python3 -m py_compile pilot/pilot.py` → без ошибок и `just build`
  → успешно. `just test` и `just vet` ранее завершились успешно; `just ui-check`
  падает на девяти lint-ошибках в неизменённых UI-файлах, а `npm test -- --run` —
  на четырёх существующих UI-тестах (98 всего).
- Next action: владелец UI должен восстановить зелёный `just ui-check` и UI-тесты,
  затем повторить Verify. Более широкий fallback при ошибках, не похожих на лимит,
  остаётся отдельным решением (см. спецификацию).

## LOG

### 2026-08-08 — Specification

Проверены `pilot/pilot.py`, `intake/app.py`, экран `Access` и `Overview`.
`brain()` используется для решений конвейера и голосовой постановки; он читает
`limits.json`, а `stage_worker()` уже исключает заблокированного провайдера при
выборе исполнителя этапа. Ветка предыдущей остановленной спецификации больше
не существует на `origin`, поэтому её нельзя безопасно перенести; план составлен
по текущему `main` и фактическому коду.

### 2026-08-08 — Implement

Исправлен единственный вызов `note_limit(eng.get("provider", ""), both[:200])`
на `note_limit(conf, eng.get("provider", ""), both[:200])` в `pilot/pilot.py`.
До фикса конфигурация не передавалась, `note_limit` падал с `TypeError`
(ловился общим `except`), запись о лимите не создавалась, и следующий запрос
снова начинал с уже исчерпанной подписки.

Добавлен `BrainFallbackTest` в `pilot/test_pilot.py`: мокает `load_limits`,
`note_limit`, `save` и `subprocess.run` (без реального CLI, сети или
`/opt/factory-data`). Первый вызов `brain()` — Codex получает rate-limit,
запись лимита получает верный `conf`/`provider`/`evidence`, Claude отвечает
сразу же с fallback. Второй вызов — Codex не запускается вовсе, Claude отвечает
без повторной траты попытки на исчерпанную подписку. Тест был красным на коде
до фикса (`AssertionError: 0 != 1` — запись лимита не происходила).

Проверено: `python3 -m unittest pilot.test_pilot` → OK;
`python3 -m py_compile pilot/pilot.py` → без ошибок.

### 2026-08-08 — Implement

После устранения внешнего сбоя продолжена ранее остановленная стадия: готовая
реализация перенесена на `factory/14902703-a11-c9268e6a-7b6` и проверена на
свежем `origin/main`. Дифф от точки ветвления по-прежнему ограничен карточкой,
спецификацией, `pilot/pilot.py` и `pilot/test_pilot.py`.

Проверено повторно: `python3 -m unittest pilot.test_pilot` → OK (2 теста);
`python3 -m py_compile pilot/pilot.py` → без ошибок.

### 2026-08-08 — Verify

После перебазирования на свежий `origin/main` подтверждены все критерии
переключения: изолированный `BrainFallbackTest` записывает лимит Codex с
исходной конфигурацией, возвращает Claude в первом вызове и не запускает Codex
во втором. `python3 -m unittest pilot.test_pilot` завершился OK (2 теста),
`python3 -m py_compile pilot/pilot.py` и `just build` завершились успешно;
`just test` и `just vet` также зелёные.

Полный UI-набор не даёт выдать PASS: `just ui-check` сообщает девять lint-ошибок
в `web/src/Live.tsx`, `Pipeline.tsx` и `Say.tsx`, которых нет в диффе карточки;
`npm test -- --run` завершился с 4 падениями из 98 (Overview, Settings и
TaskDetail). Эти результаты не затрагивают путь `brain()`, но требуют отдельной
починки или актуализации UI-проверок до повторной верификации.

# CARD-0034 — Мозг конвейера переключается после лимита подписки

## HEAD

- Status: Implemented, tests green.
- Branch: `factory/58c76aa1-b85-1ccdbaaa-beb`.
- Head commit: `3dc894e`.
- What changed: `pilot.brain()` теперь передаёт `conf` в `note_limit()` при
  срабатывании rate-limit, поэтому блок реально сохраняется в `limits.json`.
  Добавлен тест `BrainFallbackTest`, который сначала бьёт исчерпанного Codex
  во втором вызове `brain()` (красный без фикса), затем подтверждает, что он
  больше не запускается, пока Claude отвечает сразу.
- Evidence: `python3 -m unittest pilot.test_pilot` → OK (2 теста);
  `python3 -m py_compile pilot/pilot.py` → без ошибок; тест вручную
  проверен красным на коде до фикса (`git stash` кода `pilot.py`).
- Next action: нет — маленький слайс закрыт. Более широкий fallback при
  ошибках, не похожих на лимит, остаётся отдельным решением (см. спецификацию).

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

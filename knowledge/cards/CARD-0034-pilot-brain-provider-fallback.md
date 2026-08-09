# CARD-0034 — Мозг конвейера переключается после лимита подписки

## HEAD

- Status: DEPLOYED: переключение провайдеров выпущено из `main`; естественный
  живой fallback ещё не наблюдался, потому что активный Claude отвечает первым.
- Branch: `factory/9282fb82-de4-c2771913-08b`.
- Head commit: `4305787` (реализация, тесты и выпущенный сквош-коммит).
- What changed: `pilot.brain()` передаёт `conf` в `note_limit()` при rate-limit,
  и `BrainFallbackTest` доказывает немедленный переход с Codex на Claude и
  исключение заблокированного Codex при следующем вызове.
- Evidence: `python3 -m unittest pilot.test_pilot` → OK (13 тестов),
  `python3 -m py_compile pilot/pilot.py` → успешно; `fx factory release` собрал
  и установил `4305787`, `factory-pilot` активен. В `brain_state.json` после
  выпуска записан обычный ответ Claude (`fallback: false`), оба провайдера
  имеют состояние `ok`.
- Next action: при естественном исчерпании активного провайдера подтвердить
  `fallback: true` в `brain_state.json` и событие `BRAIN FALLBACK` в журнале.

## LOG

### 2026-08-09 — Implement

- Реализация и 13 целевых тестов перенесены на назначенную ветку поверх свежего
  `origin/main`; diff ограничен четырьмя файлами задачи.
- `python3 -m unittest pilot.test_pilot` и
  `python3 -m py_compile pilot/pilot.py` завершились успешно.
- Сквош-коммит `4305787` доставлен в `main`; `fx factory release` успешно
  собрал интерфейс и сервер, установил пилот и подтвердил, что он жив.
- Естественный fallback после выпуска не возник: первым отвечает Claude,
  состояния Claude и Codex — `ok`; искусственно менять боевую цепочку не стали.

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

### 2026-08-08 — Implement

По утверждённому решению владельца создана отдельная pipeline-задача на весь
фактически воспроизводимый набор общих UI-сбоев: девять lint-ошибок в
`Access.tsx`, `Live.tsx`, `Pipeline.tsx`, `Say.tsx` и четыре падения тестов в
`App.test.tsx`, `Overview.test.ts`, `Settings.test.tsx`. Первый Triage остановился
на уточнении расхождения имён файлов; уточнённая задача
`f39669c8-84ab-436f-9794-110cc1206a1b` запущена с критерием нулевого кода для
`just ui-check` и `npm test -- --run`.

Текущие четыре файла не смешивались с UI-исправлениями. Повторный rebase и
полный Verify отложены до появления отдельного исправления в `origin/main`, как
прямо потребовал владелец.

### 2026-08-08 — Implement

Проверено состояние зависимости после `git fetch origin`: коммита `f39669c8`
в `origin/main` ещё нет (HEAD main — `8bd6bd1`). По утверждённому решению
владельца этап зафиксирован как выполненный со стороны реализации; код и тесты
не запускались повторным полным кругом.

Открытое продолжение явно закреплено: проверки после слияния `f39669c8` —
только rebase и полный Verify, без повторной переделки готового кода.

### 2026-08-09 — Verify

| Критерий | Команда/проверка | Результат |
| --- | --- | --- |
| Лимит Codex сохраняется с исходной конфигурацией | `python3 -m unittest pilot.test_pilot` | OK, 13 тестов; `BrainFallbackTest` фиксирует вызов `note_limit(conf, ...)`. |
| Первый запрос переходит на Claude | тот же изолированный тест | В выводе дважды `BRAIN FALLBACK: отвечает claude/fable`; тест проверяет ответ Claude после лимита Codex. |
| Следующий запрос не тратит попытку Codex | тот же изолированный тест | OK; мок Codex не вызывается при втором обращении. |
| Код пилота синтаксически корректен | `python3 -m py_compile pilot/pilot.py` | Успех. |
| Серверная сборка и регрессии | `just test`, `just vet`, `just build` | Успех. |
| Полный штатный набор | `just check` | BLOCKED на `format-check`: в рабочем дереве есть неотформатированный Go-код вне диффа этой ветки. |
| Живой выпуск содержит изменение | `sudo -n /usr/local/bin/fx factory release-info`, `git merge-base --is-ancestor HEAD origin/main` | Нет: выпуск от 00:23 CDT собран из `main` на `0db5ca9`; проверяемый HEAD не является предком `origin/main`. |
| Журнал живого сервера показывает fallback | `sudo -n /usr/local/bin/fx factory logs 200` | Нет записей `BRAIN FALLBACK`, `codex`, `claude` или rate-limit; это ожидаемо, пока изменение не влито. |

Сервис после выпуска активен: `fx factory status` показывает `active (running)`.

### 2026-08-08 — Implement

После обязательного rebase на `origin/main` сохранены новый тест переключения и
добавленные в main тесты патруля. Целевые обещания спецификации подтверждены:
`python3 -m unittest pilot.test_pilot` → OK (8 тестов),
`python3 -m py_compile pilot/pilot.py` → без ошибок. Полный Verify по-прежнему
назначен после слияния `f39669c8` и в этом заходе не повторялся.

Поверх снимка `1eb0d52` лежит только правка самой этой карточки.

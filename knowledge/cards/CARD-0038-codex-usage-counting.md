# CARD-0038 — Научить счётчик денег читать логи Codex

## HEAD

- Status: ready for review — целевые проверки и сборка проходят; сбои общего
  gate воспроизведены на чистом `origin/main` вне диффа карточки.
- Branch: `factory/89e04832-28f-bc4000bc-ecc`.
- Head commit: `8261efe` (проверенная ревизия до текущего обновления карточки).
- What changed: общий счётчик читает rollout-журналы Codex, применяет точный
  версионированный API-тариф и включает известную сумму в дневной предохранитель.
- What changed: обзор показывает общие токены Codex; неизвестная модель даёт
  «стоимость не определена», а не ложный ноль.
- Evidence: `python3 -m unittest pilot.test_pilot.CodexUsageTests` → 3/3 OK;
  `npm test -- --run src/Overview.test.ts` → 9/9 passed; `npm run build` → passed.
- Evidence: `just check` доходит до двух прежних ошибок `staticcheck`; на чистом
  `origin/main` те же две ошибки и те же 3/3 сбоя `Dialog.test.tsx`.
- Next action: сохранить `attempt_id` рядом с session id при запуске Codex,
  прежде чем показывать его расход у конкретной задачи.

ГОТОВО-КОГДА: файл pilot/pilot.py
ГОТОВО-КОГДА: файл pilot/test_pilot.py
ГОТОВО-КОГДА: файл web/src/Overview.tsx
ГОТОВО-КОГДА: команда python3 -m unittest pilot.test_pilot.CodexUsageTests
ГОТОВО-КОГДА: команда cd web && npm test -- --run src/Overview.test.ts

## LOG

### 2026-08-09 — Specification

Владелец утвердил расчётную API-стоимость по точному имени модели, отдельные
цены входа, кэшированного входа и выхода, запрет подстановки похожей модели и
запрет распределять стоимость подписки между задачами.

### 2026-08-09 — Implement

Добавлены чтение событий Codex без двойного счёта накопительных итогов,
версионированный тариф OpenAI на дату реализации, общий дневной учёт и честное
отображение неизвестной цены. Три серверных и девять UI-тестов проходят,
production-сборка web завершилась успешно.

### 2026-08-09 — Implement

На финальной истории весь Python-набор пилота прошёл 27/27, Go tests,
tooling/launcher и обе сборки прошли. Общий `just check` не зелёный из-за двух
staticcheck-ошибок в `internal/controlplane` и трёх тестов `Dialog.test.tsx`;
ни один из этих файлов не входит в дифф CARD-0038.

### 2026-08-09 — Implement

Работа перенесена на ветку `factory/89e04832-28f-bc4000bc-ecc` поверх свежего
`origin/main`. Целевые проверки прошли 3/3 и 9/9, production-сборка успешна.
Две ошибки `staticcheck` и три сбоя `Dialog.test.tsx` одинаково воспроизведены
на ветке и в чистом экспорте `origin/main`; затронутых ими файлов нет в диффе.

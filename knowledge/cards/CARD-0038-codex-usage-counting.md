# CARD-0038 — Научить счётчик денег читать логи Codex

## HEAD

- Status: ready for repeat review — область осознанно включает актуальный
  production bundle; целевые проверки и production-сборка проходят.
- Branch: `factory/82b68a42-1d7-1f10a897-746`.
- Head commit: `097e723` (проверенная реализация до обновления карточки).
- What changed: тариф учитывает контекст свыше 272K и cache writes; при
  отсутствии данных о записи кэша сумма явно названа базовой оценкой.
- What changed: cumulative total обновляется при каждом событии, поэтому
  смешанный поток `last_token_usage`/`total_token_usage` не удваивает расход.
- Evidence: `python3 -m unittest pilot.test_pilot.CodexUsageTests` → 5/5 OK;
  `npm test -- --run src/Overview.test.ts` → 9/9 passed; `npm run build` → passed.
- Evidence: `just check` блокируют две прежние ошибки `staticcheck` вне диффа
  карточки: `cards_http.go:37` (U1000), `pilot_config.go:132` (SA4006).
- Evidence: повторный `npm run build` детерминированно создаёт
  `index-FwC9R2L7.js`; его SHA-1 совпадает с production bundle в реализации.
- Next action: повторить Review поставки CARD-0038 с расширенной областью.

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

### 2026-08-09 — Implement

После REQUEST CHANGES добавлены множители длинного контекста GPT-5.6, цена
cache writes и честная пометка базовой оценки при неполном rollout. Сохранение
cumulative total исправлено для смешанного потока. Серверные тесты 5/5, UI
9/9 и production-сборка прошли; общий gate по-прежнему блокируют две прежние
`staticcheck`-ошибки вне диффа CARD-0038.

### 2026-08-09 — Implement

Из повторной поставки удалён чужой `index-FwC9R2L7.js`; после rebase дифф
содержит только восемь заявленных файлов CARD-0038. Целевые проверки прошли
5/5 и 9/9, production-сборка успешна; `just check` по-прежнему останавливают
две прежние ошибки `staticcheck` вне области карточки.

### 2026-08-09 — Implement

Повторная production-сборка доказала, что `index-FwC9R2L7.js` создаётся из
актуального `Overview.tsx`, а `index.html` ссылается на него; без файла экран
не загружается. Bundle возвращён, область поставки осознанно расширена и будет
явно объявлена при сдаче.

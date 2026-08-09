# CARD-0038 — Научить счётчик денег читать логи Codex

## HEAD

- Status: implemented and verified — ready for repeat Review.
- Branch: `factory/2e2ee91d-13b-761b25c2-2d9`.
- Head commit: `6cc2552` (implementation on fresh `origin/main`).
- What changed: rollout безопасно пропускает неверные JSON-типы и сохраняет
  смещение перед недописанной строкой, чтобы прочитать её после дозаписи.
- What changed: production bundle пересобран и согласован с `dist/index.html`.
- Evidence: `python3 -m unittest pilot.test_pilot.CodexUsageTests` → 8/8 OK.
- Evidence: `npm run typecheck` → passed; `npm run build` → passed and bundle exists.
- Evidence: `npm test -- --run src/Overview.test.ts` → 9/9 passed;
- Next action: повторить Review CARD-0038 по чистому diff от точки ветвления.

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

### 2026-08-09 — Implement

После повторного REQUEST CHANGES парсер переведён на фактическое поле
`cache_write_input_tokens`. Добавлены инкрементальное чтение rollout по
смещениям и единый снимок для суток, недели и дневного лимита. Серверные тесты
прошли 6/6, UI-тесты 9/9, production-сборка завершилась успешно; отдельный тест
подтверждает, что неизменённый журнал открывается только один раз.

### 2026-08-09 — Implement

После REQUEST CHANGES работа заново перенесена на свежий `origin/main` без
посторонней CARD-0039. Парсер пропускает неверные типы, а незавершённая JSONL-
строка читается после дозаписи; это подтверждают 8/8 серверных тестов. Проверка
типов, 9/9 UI-тестов и production-сборка прошли, созданный JS-бандл существует.

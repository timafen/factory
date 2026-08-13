# CARD-0131 — «Сделано недавно»: влитое отдельно и даты по-человечески

Implementation commit: e63687448b95dbfbb0f6d9649cea7caf51e02172 — подтверждённые слияния и остановки разделены, даты и причины понятны владельцу.

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/1172f160-a6b-becf7b8a-6a3`.
- Implementation commit: e63687448b95dbfbb0f6d9649cea7caf51e02172 — подтверждённые слияния и остановки разделены, даты и причины понятны владельцу.
- What changed: dashboard выдаёт независимые группы `merged` и `failed`; receipt остаётся единственным доказательством влития.
- What changed: обзор показывает «Влито» и «Остановилось», локальные даты, этап и причину без ID, статусов и ISO-фрагментов.
- Evidence: `python3 -m unittest -v pilot.test_pilot` → 253 passed, 13 skipped; 2 failures reproduce on pinned `main` in `CorrectionProvenanceStormTests`.
- Evidence: `npm ci && npm test && npm run lint && npm run build` → 179 tests in 15 files, lint and production build passed.
- Next action: влить ветку и визуально проверить обзор на свежем dashboard-снимке.

## LOG

### 2026-08-13 — Implement

Серверный контракт разделён на подтверждённые receipt-слияния и `failed`/`cancelled`
остановки с независимым лимитом пяти записей. Интерфейс показывает человеческие
даты, этап и причину, а контрактная и UI-регрессии подтверждают, что пять новых
провалов не скрывают четыре влитые работы.

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| Влитое не смешано с остановками | `RecentDoneTest` и полный UI-набор | receipt даёт только «Влито», `failed`/`cancelled` — только «Остановилось» |
| Свежие провалы не скрывают влитое | `test_separates_merged_and_failed_with_independent_limits` | 4 влитые и 5 остановок сохраняются независимыми лимитами |
| Подписи и даты читаются человеком | `Overview.test.ts` | видны «Влито в main», этап и причина; сегодня/вчера/локальная дата без ISO-фрагментов |

Полный веб-набор прошёл: 179 тестов в 15 файлах, lint и production build успешны.
Python-набор: 253 passed, 13 skipped, 2 ошибки `CorrectionProvenanceStormTests` воспроизводятся на закреплённом `main` и не относятся к изменению обзора.

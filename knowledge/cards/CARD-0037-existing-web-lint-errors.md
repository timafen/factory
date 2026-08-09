# CARD-0037 — Устранить старые lint-ошибки web-интерфейса

## HEAD

- Status: planned — отдельная задача, не блокирует CARD-0036 по решению владельца.
- Branch: не назначена.
- Head commit: `5520a47` (снимок, на котором подтверждён долг).
- What changed: выделены девять воспроизводимых lint-ошибок, не относящихся к
  очистке завершённых карточек Плана.
- Evidence: `cd web && npm run lint` сообщает 9 errors и 7 warnings; целевые
  `Overview.test.ts` и `Settings.test.tsx` проходят 14/14.
- Next action: исправить перечисленные ошибки и добиться нулевого кода lint.

ГОТОВО-КОГДА: файл web/src/Access.tsx
ГОТОВО-КОГДА: файл web/src/Live.tsx
ГОТОВО-КОГДА: файл web/src/Pipeline.tsx
ГОТОВО-КОГДА: файл web/src/Say.tsx
ГОТОВО-КОГДА: команда cd web && npm run lint

## LOG

### 2026-08-09 — Triage

`npm run lint` воспроизводит девять ошибок:

- `Access.tsx:35:26`, `Live.tsx:38:10`, `Pipeline.tsx:31:34` — синхронный
  `setState` внутри effect;
- `Say.tsx:137:7` — тот же `setState` внутри effect;
- `Say.tsx:181:14`, `227:14`, `244:14`, `263:14` — неиспользуемая переменная
  `e`;
- `Say.tsx:406:54` — чтение ref во время render.

Два сбоя из отчёта предыдущей проверки больше не воспроизводятся:
`Overview active work` и шесть сценариев `Settings.test.tsx` проходят; весь
целевой запуск двух файлов — 14/14. Поэтому CARD-0037 ограничена оставшимся
lint-долгом.

# CARD-0053 — Завершение подзадач эпика переживает очистку истории

## HEAD

Status: Implemented — готово к проверке и слиянию.
Branch: `factory/e6a73fe0-450-d846e2b1-caa`.
Implementation commit: `68761c3e98f1a92a22419e92a1131c426bd9bf1f` — Пилот восстанавливает завершённую подзадачу из legacy-квитанции после очистки истории.
What changed: Разбор квитанции явно снимает только конечный UTC-суффикс и сохраняет поддержку старой локальной даты merge-журнала.
Регрессия подтверждает, что такая свежая точная квитанция переводит running-подзадачу в `done` после очистки истории.
Evidence: `python3 -m unittest pilot.test_pilot.EpicCompletionReceiptTests` — 8 tests OK; `python3 -m unittest pilot.test_pilot` — 146 tests OK; `just build` — OK.
One next action: проверить и влить ветку в `main`.

## LOG

### 2026-08-10 — Implement

В ветке завершения подзадач эпика обнаружены три файла вне заявленной области. Они возвращены к состоянию `origin/main`; после rebase предметный diff пуст, пробельных ошибок нет. Риск: изменения предыдущей реализации намеренно не доставляются этой веткой, поскольку они признаны чужими.

### 2026-08-10 — Test

`python3 -m unittest pilot.test_pilot` завершилась успешно: 108 проверок. После финального rebase трёхточечное сравнение с `origin/main` содержит только эту карточку, поэтому изменения пилота и общего журнала не попадут в поставку.

### 2026-08-10 — Implement

Поставка заново собрана от актуального `origin/main` в ветке `factory/5c81b54b-8ce-ada87c5a-c78`. В HEAD карточки устаревающий хеш заменён содержательным итогом: ветка доставляет только CARD-0053 и не возвращает изменения пилота или общего журнала. Проверка `python3 -m unittest pilot.test_pilot` прошла: 108 проверок; трёхточечный diff и проверка пробелов подтверждают чистый состав поставки.

### 2026-08-10 — Verify

| Критерий | Команда / проверка | Результат |
| --- | --- | --- |
| Очистка истории не возвращает чужие файлы | `git diff --name-only origin/main...HEAD` | Только `knowledge/cards/CARD-0053-epic-subtask-history-cleanup.md`. |
| Поставка собрана от актуального `main` | `git fetch origin main` и `git reset --hard origin/main` до переноса карточки | Выполнено; старая ветка использована только как источник этой карточки. |
| Проверка типов UI | `cd web && npx tsc -p tsconfig.app.json --noEmit` | OK. |
| Полные серверные и пилотные проверки | `go test -timeout 5m ./...`; `go vet ./...`; `python3 -m unittest pilot.test_pilot` | OK; Go: 13 пакетов, Pilot: OK. |
| UI-проверка | `npm run lint`; `npm run typecheck`; `npm test` | lint и typecheck — OK; полный Vitest: 122/123, один нестабильный сбой в `src/App.test.tsx` вне области поставки; повтор `npx vitest run src/App.test.tsx` — 63/63 OK. |
| Нет пробельных артефактов | `git diff --check origin/main...HEAD` | OK. |

### 2026-08-10 — Implement

Полная реализация перенесена из `factory/f038362a-a18-27b85255-e35` поверх
свежего `origin/main`: только `pilot/pilot.py` и `pilot/test_pilot.py`.
`4e40ff2` сохраняет durable receipt, отсеивает старый merge после `failed` и
`stuck`, и не меняет семантику `hold_reason` и `parallel_ok`.
`python3 -m unittest pilot.test_pilot` — 115 OK; `just build` — OK.

### 2026-08-10 — Implement

Legacy merge-квитанция с локальной датой без `Z` вновь подтверждает завершение
running-подзадачи после очистки истории; снятие UTC-суффикса сделано явным.
`python3 -m unittest pilot.test_pilot.EpicCompletionReceiptTests` — 8 OK;
`python3 -m unittest pilot.test_pilot` — 146 OK; `just build` — OK.

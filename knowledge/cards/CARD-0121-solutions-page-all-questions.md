Implementation commit: b28bc152cd9968148365b057055907e7319e65ef — отдельная read-only страница `/solutions` со всей историей вопросов.

# CARD-0121 — Страница «Решения» со всеми вопросами

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/1ff8d702-32b-eaa842a1-d1e`.
- Implementation commit: b28bc152cd9968148365b057055907e7319e65ef — отдельная read-only страница `/solutions` со всей историей вопросов.
- What changed: пункт «Решения» открывает отдельный список всех вопросов и сохранённых ответов; действия владельца остались только в очереди «Нужен ответ».
- Evidence: pinned-сравнение `fa98244835641826e5e682e938b88ca8f7dddb80...1b2c3f083736dcbb388e749cf4dc9f0fdfdabf78`; `go test ./...` passed; Vitest — 16 файлов и 175 тестов passed; typecheck, lint и production build passed, `dist` совпал; один старый Playwright-сбой воспроизведён на базе без кандидата.
- Next action: человеку влить ветку в `main`.

## LOG

### 2026-08-13 — Implement

На свежий `main` перенесены маршрут `/solutions`, пункт меню и read-only история вопросов всех статусов. Целевые тесты подтвердили отдельную навигацию, отображение открытых, отвеченных, решённых, устаревших и неизвестных статусов, а также отсутствие кнопок ответа и мутаций; typecheck, lint и production build завершились успешно.

### 2026-08-13 — Verify

| Критерий | Команда / проверка | Наблюдаемый результат |
| --- | --- | --- |
| «Решения» — отдельный экран, а «Нужен ответ» не заменён | `npm test` (`App.test.tsx`) | `/solutions` активирует отдельный пункт; переход в `/answer` сохраняет отдельную очередь. |
| Показаны все вопросы и сохранённые решения | `npm test` (`Solutions.test.tsx`) | Показаны open, answered, resolved, stale и неизвестный статус, ситуация, вопрос, ответ и автор. |
| История доступна только для чтения | `npm test` (`Solutions.test.tsx`) | Кнопок решения/отправки нет; POST и DELETE не выполняются. |
| Смежная очередь ответов не сломана | `npm test` (`Answer.test.tsx`) | Выбор решения и отправка ответа проходят; весь Vitest: 16 файлов, 175 тестов passed. |
| Backend-регрессии | `go test ./...` | Все Go-пакеты passed, включая `internal/controlplane` и `internal/worker`. |
| Статика и поставленный frontend | `npm run typecheck`; `npm run lint`; `npm run build`; SHA-256 сравнение `dist` до/после | Все команды passed; production `dist` совпал байт-в-байт. |
| Browser-регрессии | `npm run test:browser`; затем тот же упавший test на base SHA | 5 e2e passed; старый тест `/work` ожидает «Работа агентов» вместо фактического «Работа» и так же падает на `main` без кандидата. |

Открытый риск: `npm ci` сообщает о двух high-severity уязвимостях зависимостей; миграций и ручных шагов для этой поставки нет.

Implementation commit: 490bf238af4be2c84b337eed29a252158799ea74 — отдельная read-only страница `/solutions` со всей историей вопросов.

# CARD-0121 — Страница «Решения» со всеми вопросами

## HEAD

- Status: Verified PASS — awaiting human merge.
- Branch: `factory/b5b9bee6-002-bc12ef09-98b`.
- Implementation commit: 490bf238af4be2c84b337eed29a252158799ea74 — отдельная read-only страница `/solutions` со всей историей вопросов.
- Evidence summary: меню и маршрут «Решения» открывают историю всех статусов, а действия остаются только на «Нужен ответ»; полный прогон дал 175 passed, typecheck, lint и production build завершились успешно.
- Next action: вручную открыть `/solutions` на стенде с реальными вопросами после установки staging-команд `seller-policies` и `listings`.

## LOG

### 2026-08-13 — Implement

Добавлены `/solutions`, отдельный пункт меню и read-only список всех валидных вопросов API, включая неизвестные статусы и сохранённые ответы. Целевые тесты подтверждают все статусы, отсутствие кнопок и мутаций; typecheck, lint и production build завершились успешно.

### 2026-08-13 — Verify

| Критерий | Проверка | Результат |
| --- | --- | --- |
| `/solutions` — отдельный список всех вопросов | `npm test` | 16 test files, 175 tests passed |
| Все статусы, даты, вопросы, ситуации и ответы отображаются; действия не дублируются | `npm test` (включает `Solutions.test.tsx`, `App.test.tsx`, `Answer.test.tsx`) | passed |
| Код собирается и не содержит ошибок типов/линтера | `npm run typecheck`; `npm run lint`; `npm run build` | passed; build завершён |
| Живой экран на staging | `sudo -n /usr/local/bin/fx staging sandbox bootstrap-accounts | seller-policies | listings` | BLOCKED: команды `seller-policies` и `listings` отсутствуют в worker |

Проверка выполнена относительно base `cd5c93b488fe6f7694f59d1e6b8d5e5abd58af91` и candidate `23a8b2a636d1a502611e89d4b1818099dd0e55bb`; рабочее дерево чистое.

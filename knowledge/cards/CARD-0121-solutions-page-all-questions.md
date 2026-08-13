Implementation commit: 490bf238af4be2c84b337eed29a252158799ea74 — отдельная read-only страница `/solutions` со всей историей вопросов.

# CARD-0121 — Страница «Решения» со всеми вопросами

## HEAD

- Status: Implemented.
- Branch: `factory/b5b9bee6-002-bc12ef09-98b`.
- Implementation commit: 490bf238af4be2c84b337eed29a252158799ea74 — отдельная read-only страница `/solutions` со всей историей вопросов.
- What changed: меню и маршрут «Решения» открывают историю всех статусов; действия остаются только на «Нужен ответ».
- What changed: общий `OwnerQuestion` сохраняет единый контракт API для очереди и истории.
- Evidence: `npm test -- --run src/Solutions.test.tsx src/App.test.tsx src/Answer.test.tsx` → 66 tests passed; `npm run typecheck`, `npm run lint`, `npm run build` → passed.
- Next action: открыть `/solutions` на стенде с реальными вопросами и визуально проверить историю.

## LOG

### 2026-08-13 — Implement

Добавлены `/solutions`, отдельный пункт меню и read-only список всех валидных вопросов API, включая неизвестные статусы и сохранённые ответы. Целевые тесты подтверждают все статусы, отсутствие кнопок и мутаций; typecheck, lint и production build завершились успешно.
